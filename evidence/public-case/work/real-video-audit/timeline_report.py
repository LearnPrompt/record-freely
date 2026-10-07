#!/usr/bin/env python3
"""Summarize redactor evidence without storing recognized URL text."""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

ORIGIN_LABELS = {'ocr': '首轮当前帧 OCR', 'tracked': '首轮正向模板跟踪补框',
                 'backfilled': '首轮向前帧回填', 'review_roi_ocr': '人工复核指定区域后的局部 OCR 补码',
                 'review_glyph_template': '人工复核字形模板收紧补码',
                 'review_template': '人工复核模板补码', 'review_color_line': '人工复核颜色行补码',
                 'review_temporal_bridge': '人工复核短时间缺口桥接补码'}
METHOD_LABELS = {'characters': '首轮按网址字符范围定位', 'line_fallback': '首轮字符定位失败时整行回退',
                 'reviewed_word': '复核词范围框（含局部 OCR 与字形模板）', 'reviewed_characters': '复核字符范围框',
                 'reviewed_template_word': '复核字形模板词范围框',
                 'reviewed_template': '复核模板匹配框', 'reviewed_color_line': '复核颜色行范围框',
                 'reviewed_temporal_bridge': '复核短时间桥接框'}


def review_count(counts):
    return sum(value for key, value in counts.items() if key.startswith('review_'))


def reviewed_method_count(counts):
    return sum(value for key, value in counts.items() if key.startswith('reviewed_'))


def stamp(seconds):
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    seconds, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{millis:03}"


def center(box):
    x, y, w, h = box
    return x + w / 2, y + h / 2


def distance(a, b):
    ac, bc = center(a), center(b)
    return math.hypot(ac[0] - bc[0], ac[1] - bc[1])


def intersects(a, b):
    return (max(a[0], b[0]) < min(a[0] + a[2], b[0] + b[2])
            and max(a[1], b[1]) < min(a[1] + a[3], b[1] + b[3]))


def summarize(report, jump_floor=160, movement_threshold=10, size_threshold=1.1):
    fps = float(report['fps'])
    if fps <= 0:
        raise ValueError('fps must be positive')
    cuts = {int(c['frame']) if isinstance(c, dict) else int(c)
            for c in report.get('scene_cuts', [])}
    frames = sorted(report['frames'], key=lambda f: int(f['frame']))
    events, active, intervals = [], [], []
    methods, origins, scales = Counter(), Counter(), Counter()
    scales_by_origin = {}
    total_regions = masked_frames = 0
    previous_frame = None
    for frame in frames:
        number = int(frame['frame'])
        boxes = frame.get('boxes', [])
        regions = frame.get('regions', [])
        source_origins = frame.get('origins', [])
        if len(regions) != len(boxes):
            raise ValueError(f'Frame {number}: region and box counts differ')
        if previous_frame is not None and number <= previous_frame:
            raise ValueError('Frame indices must be unique and increasing')
        previous_frame = number
        if boxes:
            masked_frames += 1
            if intervals and intervals[-1]['last_frame'] == number - 1:
                intervals[-1]['last_frame'] = number
            else:
                intervals.append({'first_frame': number, 'last_frame': number})
        active = [e for e in active if e['_last_frame'] == number - 1 and number not in cuts]
        available = list(active)
        next_active = []
        candidates = []
        for i, (box, region) in enumerate(zip(boxes, regions)):
            if len(box) != 4 or min(box[2:]) <= 0:
                raise ValueError(f'Frame {number}: invalid box')
            identity = region.get('id') or 'unidentified'
            for event in available:
                if event['link_id'] != identity:
                    continue
                old = event['_last_box']
                dist = distance(old, box)
                limit = max(jump_floor, 3 * max(old[3], box[3]), .5 * max(old[2], box[2]))
                if intersects(old, box) or dist <= limit:
                    candidates.append((dist, i, event['event_id']))
        matches, used = {}, set()
        event_lookup = {e['event_id']: e for e in available}
        for _, index, event_id in sorted(candidates):
            if index not in matches and event_id not in used:
                matches[index] = event_lookup[event_id]
                used.add(event_id)
        for i, (box, region) in enumerate(zip(boxes, regions)):
            origin = region.get('origin') or (source_origins[i] if i < len(source_origins) else 'unknown')
            method = region.get('box_method', 'unknown')
            event = matches.get(i)
            if event is None:
                event = {'event_id': f'E{len(events) + 1:04}',
                         'link_id': region.get('id') or 'unidentified',
                         'first_frame': number, 'last_frame': number,
                         'origins': Counter(), 'box_methods': Counter(), 'kinds': Counter(),
                         'relative_scale_counts': Counter(), '_boxes': [], '_confidence': [],
                         '_scores': [], '_max_step': 0, '_last_frame': number, '_last_box': box}
                events.append(event)
            else:
                event['_max_step'] = max(event['_max_step'], distance(event['_last_box'], box))
            event['last_frame'] = event['_last_frame'] = number
            event['_last_box'] = box
            event['_boxes'].append(box)
            event['origins'][origin] += 1
            event['box_methods'][method] += 1
            event['kinds'][region.get('kind', 'unknown')] += 1
            if 'ocr_confidence' in region:
                event['_confidence'].append(float(region['ocr_confidence']))
            if 'tracking_score' in region:
                event['_scores'].append(float(region['tracking_score']))
            if 'relative_scale' in region:
                scale = str(region['relative_scale'])
                event['relative_scale_counts'][scale] += 1
                scales[scale] += 1
                scales_by_origin.setdefault(origin, Counter())[scale] += 1
            methods[method] += 1
            origins[origin] += 1
            total_regions += 1
            next_active.append(event)
        active = next_active
    for interval in intervals:
        interval.update(start=stamp(interval['first_frame'] / fps),
                        end=stamp((interval['last_frame'] + 1) / fps),
                        duration_seconds=round((interval['last_frame'] - interval['first_frame'] + 1) / fps, 6))
    area = float(report.get('width', 0)) * float(report.get('height', 0))
    flagged = []
    for event in events:
        boxes = event.pop('_boxes')
        cx, cy = zip(*(center(b) for b in boxes))
        xs, ys, widths, heights = zip(*boxes)
        width_ratio = max(widths) / min(widths)
        height_ratio = max(heights) / min(heights)
        span = math.hypot(max(cx) - min(cx), max(cy) - min(cy))
        confidence, scores = event.pop('_confidence'), event.pop('_scores')
        max_step = event.pop('_max_step')
        event.pop('_last_frame')
        event.pop('_last_box')
        event.update(start=stamp(event['first_frame'] / fps), end=stamp((event['last_frame'] + 1) / fps),
                     start_seconds=round(event['first_frame'] / fps, 6),
                     end_seconds=round((event['last_frame'] + 1) / fps, 6),
                     duration_seconds=round((event['last_frame'] - event['first_frame'] + 1) / fps, 6),
                     box_count=len(boxes), x_range=[min(xs), max(xs)], y_range=[min(ys), max(ys)],
                     width_range=[min(widths), max(widths)], height_range=[min(heights), max(heights)],
                     center_span_pixels=round(span, 2), max_center_step_pixels=round(max_step, 2),
                     width_ratio=round(width_ratio, 4), height_ratio=round(height_ratio, 4),
                     suspected_movement=span > movement_threshold,
                     detection_box_size_changed=max(width_ratio, height_ratio) > size_threshold,
                     ocr_confidence_range=[min(confidence), max(confidence)] if confidence else None,
                     tracking_score_range=[min(scores), max(scores)] if scores else None,
                     mask_area_percent_range=[round(100 * min(b[2]*b[3] for b in boxes)/area, 4),
                                              round(100 * max(b[2]*b[3] for b in boxes)/area, 4)] if area else None)
        for field in ('origins', 'box_methods', 'kinds', 'relative_scale_counts'):
            event[field] = dict(event[field])
        reasons = []
        if max(width_ratio, height_ratio) > 1.25:
            reasons.append('检测框尺寸比超过1.25，需画面核实')
        if max_step > 50:
            reasons.append('相邻框中心位移超过50像素，需画面核实')
        if event['box_methods'].get('line_fallback'):
            reasons.append('存在整行回退框，需检查遮挡范围')
        event['visual_review_reasons'] = reasons
        if reasons:
            flagged.append(event['event_id'])
    return {'schema_version': 1, 'fps': fps, 'processed_frames': len(frames),
            'processing_configuration': {k: report[k] for k in ('engine', 'style', 'padding', 'detect_every',
                                                               'hold_seconds', 'lookback_frames', 'ocr_workers',
                                                               'tld_snapshot') if k in report},
            'masked_frames': masked_frames, 'region_instances': total_regions,
            'masked_duration_seconds': round(masked_frames / fps, 6),
            'masked_frames_percent': round(100 * masked_frames / len(frames), 4) if frames else 0,
            'anonymous_candidate_id_count': len({e['link_id'] for e in events}),
            'event_count': len(events), 'continuous_masked_intervals': intervals, 'events': events,
            'origin_counts': dict(origins), 'box_method_counts': dict(methods),
            'relative_scale_counts': dict(scales),
            'relative_scale_counts_by_origin': {key: dict(value) for key, value in scales_by_origin.items()},
            'manual_review_region_instances': review_count(origins),
            'repairs_evidence': {key: report.get('repairs', {}).get(key) for key in
                                ('false_positive_regions_removed', 'reviewed_regions_added', 'glyph_row_trim_regions')
                                if key in report.get('repairs', {})},
            'origin_percent': {k: round(100*v/total_regions, 4) for k, v in origins.items()} if total_regions else {},
            'box_method_percent': {k: round(100*v/total_regions, 4) for k, v in methods.items()} if total_regions else {},
            'visual_review_event_ids': flagged,
            'thresholds': {'consecutive_frames_only': True, 'split_at_reported_scene_cuts': True,
                           'association_jump_floor_pixels': jump_floor,
                           'association_center_jump_limit': f'max({jump_floor}px, 3*max_height, 0.5*max_width); intersecting boxes also eligible',
                           'suspected_movement_center_span_pixels': movement_threshold,
                           'detection_box_size_ratio': size_threshold,
                           'visual_review_size_ratio': 1.25, 'visual_review_frame_step_pixels': 50}}


def write_outputs(report, summary, directory):
    if summary['manual_review_region_instances']:
        remaining_false_positives = {'U012', 'U015', 'U083', 'U133'} & {e['link_id'] for e in summary['events']}
        if remaining_false_positives:
            raise ValueError('Review report still contains candidates scheduled for removal: ' + ','.join(sorted(remaining_false_positives)))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / '事件摘要.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    columns = ['事件', '匿名链接ID', '开始时间', '结束时间_不含', '持续秒', '遮挡框次数', 'OCR框',
               '正向跟踪框', '回填框', '复核局部OCR框', '复核字形模板框', '复核模板框', '复核颜色行框', '复核时间桥接框',
               '字符框', '整行回退框', '复核词框', '复核字符框', '复核模板定位框', '复核颜色行定位框', '复核时间桥接定位框', '复核字形模板词定位框',
               'x范围_px', 'y范围_px', '宽范围_px',
               '高范围_px', '中心范围跨度_px', '最大相邻中心位移_px', '宽最大最小比', '高最大最小比',
               '疑似移动', '检测框大小变化_需画面核实', '跟踪相对尺寸次数', '待核实原因']
    with (directory / '时间轴.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for e in summary['events']:
            writer.writerow([e['event_id'], e['link_id'], e['start'], e['end'], e['duration_seconds'],
                             e['box_count'], e['origins'].get('ocr', 0), e['origins'].get('tracked', 0),
                             e['origins'].get('backfilled', 0),
                             e['origins'].get('review_roi_ocr', 0),
                             e['origins'].get('review_glyph_template', 0),
                             *[e['origins'].get(key, 0) for key in ('review_template', 'review_color_line', 'review_temporal_bridge')],
                             *[e['box_methods'].get(key, 0) for key in ('characters', 'line_fallback',
                                'reviewed_word', 'reviewed_characters', 'reviewed_template', 'reviewed_color_line')],
                             e['box_methods'].get('reviewed_temporal_bridge', 0),
                             e['box_methods'].get('reviewed_template_word', 0),
                             e['x_range'], e['y_range'],
                             e['width_range'], e['height_range'], e['center_span_pixels'],
                             e['max_center_step_pixels'], e['width_ratio'], e['height_ratio'],
                             '是' if e['suspected_movement'] else '否',
                             '是' if e['detection_box_size_changed'] else '否',
                             json.dumps(e['relative_scale_counts']), '；'.join(e['visual_review_reasons'])])
    n = summary['region_instances']
    has_review = summary['manual_review_region_instances'] > 0
    def share(count):
        return f'{count} 次（{100 * count / n:.2f}%）' if n else '0 次（无遮挡框）'
    lines = ['# 《带封面》前 5 分钟打码汇报' + ('（自动识别 + 人工复核修正）' if has_review else '（首轮自动识别）'), '',
             '时间均相对本次处理片段；本次为原视频从 00:00 开始。结束时间不包含在事件中，为最后一帧之后。匿名 ID 表示识别或复核确认的候选文本身份，不保存网址内容或参数。', '',
             f"- 引擎：{report.get('engine', '未记录')}；画幅 {report.get('width', '未记录')} × {report.get('height', '未记录')}；{summary['fps']:g} fps。",
             f"- 分析 {summary['processed_frames']} 帧；有遮挡 {summary['masked_frames']} 帧（合计 {summary['masked_duration_seconds']:.3f} 秒，{summary['masked_frames_percent']:.2f}%）；产生 {n} 次遮挡框，分为 {summary['event_count']} 段出现事件。",
             f"- 共 {summary['anonymous_candidate_id_count']} 个匿名候选/复核标识，含 OCR 变体与人工补框标签，不能等同真实网址数。",
             f"- 遮挡样式：{report.get('style', '未记录')}；文字框四周预设余量 {report.get('padding', '未记录')} px；OCR 检测间隔 {report.get('detect_every', '未记录')} 帧。",
             f"- 本地 OCR worker 数：{report.get('ocr_workers', '未记录')}；按原帧顺序进行跟踪、打码和输出。",
             '- 此报告记录检测与遮挡证据，不能证明所有链接均已找到。普通网址形态之外的文字、低清晰度、遮挡或识别失败仍可能漏码。', '',
             '## 首轮自动识别的判断规则', '',
             '识别 `http(s)://`、`www.` 和裸域名。裸域名用本地保存的 IANA 顶级域名列表筛选，排除不在列表内的普通代码字段，额外保留少量测试/内部域名后缀；常见文件扩展名以及形如函数调用的字段另行排除。裸域名要求 OCR 置信度至少 0.5；含 `http(s)` 或 `www` 显式前缀的候选在较低置信度时仍保留。', '',
             f"IANA 列表快照标记：`{report.get('tld_snapshot', '未记录')}`；来源：[IANA 顶级域名列表](https://data.iana.org/TLD/tlds-alpha-by-domain.txt)。视频 OCR 和候选筛选在本地执行，不联网验证识别出的地址是否有效。此筛选也不能保证所有通过的字段都是真实链接。", '',
             '首轮执行的严格排除规则仍有已知局限：`.sh`、`.zip` 等后缀既可能是文件扩展名，也可能属于真实域名；无显式前缀、无路径的裸域名后接括号时，也可能被当作代码字段排除。后续修改源码不会自动补齐已有成片；本报告只统计当前处理记录中实际存在的框。', '']
    if 'mask_area_union_estimate' in summary:
        area_stats = summary['mask_area_union_estimate']
        lines[lines.index('## 首轮自动识别的判断规则'):lines.index('## 首轮自动识别的判断规则')] = [
            f"遮罩面积参考：按 {area_stats['grid_step_pixels']} px 网格降采样估算框覆盖并集，在有遮罩的帧中，中位数 {area_stats['median_percent']:.3f}%、95 分位 {area_stats['p95_percent']:.3f}%、最大 {area_stats['max_percent']:.3f}%。橙色字幕前景保留后，实际灰色覆盖会略少；这是每帧画面的面积比例，不是总体视频时长比例。", '']
    if has_review:
        lines.extend(['## 此次人工复核修正', '',
                      '最终成片结合首轮自动识别和人工复核后的定向修正。复核项先由人工核实位置、时间与误判，再使用局部 OCR、字形模板、复核模板、颜色行或短时间桥接补框；这些项目不属于首轮模型独立自动完成的结果。', '',
                      '复核去掉四类误码：文件名候选 U012、代码字段候选 U015、导航字样候选 U083、HOME 字样候选 U133。公有域名 `models.dev` 的局部 OCR 补码重点覆盖 00:01:40.000–00:01:45.000 和 00:02:14.000–00:02:42.000 两个审阅范围；实际逐帧出现时间和最终遮挡范围按下方事件及 CSV 记录。', '',
                      '快速字幕、画面尺度变化及长蓝色链接尾部按复核模板和颜色行补码；短时间桥接只表示复核后补齐的时间缺口，不表示该帧首轮 OCR 识别成功。自动路径的 70 px 搜索和 0.87 阈值只适用于首轮跟踪，不能拿来描述这些复核补框。', '',
                      f"当前记录中共 {summary['manual_review_region_instances']} 次框来自人工复核修正。仍不能用本报告证明零漏码；高变化事件筛选是便于再看视频的提示，不等于已经确认的漏码。", ''])
        repairs = summary['repairs_evidence']
        if repairs:
            lines.append(f"处理记录的修正计数：移除 {repairs.get('false_positive_regions_removed', '未记录')} 次误码框，添加 {repairs.get('reviewed_regions_added', '未记录')} 次复核框。")
            lines.append('')
        trimmed_regions = repairs.get('glyph_row_trim_regions', 0)
        if trimmed_regions:
            lines.extend([f'观看效果的二次微调：{trimmed_regions} 次代码托管链接模板框按白色网址文字所在行、上下各 4 px 余量收窄高度。复核确认网址白字仍被覆盖，橙色字幕和下一行中文保留，并消除了下一行中文上缘被误擦的情况；其余框及遮挡次数不变。', ''])
        glyph_count = summary['origin_counts'].get('review_glyph_template', 0)
        if glyph_count:
            lines.extend([f'模型目录站点的方法句附近另有 {glyph_count} 次框采用人工复核字形模板来源，收紧词范围；其定位方法仍可记录为 reviewed_word，不应全部解释为当前帧 OCR 检出。', ''])
        lines.extend(['### 主要片段：看什么、怎么处理', '',
                      '以下为方便审阅的片段分类，范围内并非每一帧都有链接；实际打码时间由逐帧记录决定。', '',
                      '| 片段范围 | 片段类别 | 实际遮挡与处理手段 |', '| --- | --- | --- |'])
        segments = [(60, 77, '代码托管 github.com 链接与字幕/滚动片段', '首轮字符定位；快速尺度变化、滚动和字幕相交处使用复核模板补框。'),
                    (88, 94, '界面中的零星疑似链接', '首轮逐帧 OCR；框消失即按实际记录撤除。'),
                    (99, 105, '公有域名 models.dev 字样', '人工核实后指定局部 OCR 区域，增加词框与字符范围框。'),
                    (105, 134, '分享网址与界面链接', '首轮 OCR 跟随位置/尺寸更新；119 秒附近分享网址字幕使用复核模板与短时间桥接。'),
                    (134, 163, 'models.dev 与长蓝色链接', '局部 OCR 与字形模板补站点字样并收紧词框；长蓝色链接尾部通过复核颜色行补码，保留字幕观看范围。'),
                    (225, 237, '后段零星疑似文本', '按实际自动识别框遮挡；候选是否属于真实链接需结合画面确认。'),
                    (252, 255, '后段零星疑似文本', '按实际自动识别框遮挡；已确认的 HOME 导航误码已移除。')]
        for start, end, category, description in segments:
            instances = sum(len(f['boxes']) for f in report['frames'] if start <= f['frame'] / summary['fps'] < end)
            if instances:
                lines.append(f'| {stamp(start)}–{stamp(end)} | {category} | {description} 该审阅范围内 {instances} 次框。 |')
        lines.extend(['', '### 明确修正的关键时刻', '',
                      '| 时刻 / 情况 | 首轮问题与此次处理 |', '| --- | --- |',
                      '| 00:01:12.400，两处代码托管链接随画面缩放 | 首轮部分帧缺框；使用人工复核模板重新给出对应位置与尺寸，分别补齐两处链接。 |',
                      '| 00:01:13.700，字幕/滚动片段 | 用复核模板补齐短暂识别缺口；有字幕保留标记的帧按字幕前景合成处理。 |',
                      '| 00:01:59.267，分享网址与字幕相交 | 使用复核模板补框，极短时间缺口另用 review_temporal_bridge 记录；桥接不算首轮识别成功。 |',
                      '| 00:02:40.000 与 00:02:41.567，长蓝色链接尾部 | 原字符框尾部不足；用人工复核的颜色行范围补齐长蓝色文本，具体框大小随逐帧记录变化。 |', ''])
    lines.extend(['## 实际方法和占比', '', '| 遮挡框的来源 | 实际次数与占比 |', '| --- | --- |'])
    for key, name in ORIGIN_LABELS.items():
        lines.append(f'| {name} | {share(summary["origin_counts"].get(key, 0))} |')
    lines.extend(['', '| 文字定位方式 | 实际次数与占比 |', '| --- | --- |'])
    for key, name in METHOD_LABELS.items():
        lines.append(f'| {name} | {share(summary["box_method_counts"].get(key, 0))} |')
    lines.extend(['', '占比分母为全部遮挡框次数；同一帧可能有多个框，不能把这些比例解释为视频时长比例。跟踪及回填继承初始 OCR 的文字定位方式。', '',
                  '## 移动、放大、缩小的处理', '',
                  '首轮自动路径中，当前帧 OCR 检测会重新给出网址的位置和尺寸，遮罩跟着该帧的框更新。OCR 暂时未检出时，OpenCV 在上一框周围 70 px 搜索匹配，分别尝试模板尺寸 1.00、0.94、1.06 倍，归一化相关分数至少 0.87 才接受。该尺寸倍数是这一次模板匹配的选择，不能直接当作镜头缩放倍数。', '',
                  '短暂识别缺口采用正向匹配补框；新检出时也会向已缓存的前帧反向匹配回填，仍要求每一帧有匹配证据。检测到切镜时清空跟踪，重新检测。若移动超出搜索区域或缩放不在模板尝试范围且 OCR 也失败，当前实现可能中断遮罩，因此高变化事件须视觉复核。', '',
                  f"本次正向跟踪允许的 OCR 缺口上限为 {report.get('hold_seconds', '未记录')} 秒"
                  + (f"（参数换算为 {round(report['hold_seconds'] * summary['fps'])} 帧）" if 'hold_seconds' in report else '')
                  + f"；反向回填缓存实际为 {report.get('lookback_frames', '未记录')} 帧"
                  + (f"（最多向前 {report['lookback_frames'] / summary['fps']:.3f} 秒，受 96 MiB 内存上限限制）" if 'lookback_frames' in report else '（缓存内存上限为 96 MiB）')
                  + '。这是可尝试的上限，实际接受的框数见本报告统计；匹配不足时不会强行保留遮罩。', '',
                  f"实际记录的模板相对尺寸计数（各来源合计）：`{json.dumps(summary['relative_scale_counts'], ensure_ascii=False)}`；按来源细分：`{json.dumps(summary['relative_scale_counts_by_origin'], ensure_ascii=False)}`。",
                  '', '检测框位置变化只标为疑似移动；检测框尺寸变化也可能来自 OCR 框抖动、字符范围改变或整行回退，必须看画面才能确认真实放大或缩小。', '',
                  '## 全部疑似链接出现事件', '',
                  '同一匿名链接在同一帧出现于多个位置，会形成不同事件；切镜、消失一帧及空间明显断开均分段。因此以下事件段数不等于不同网址数量。坐标为左上角 x/y，尺寸为像素范围。', '',
                  '| 事件 / ID | 起止（结束不含） | OCR / 跟踪 / 回填 / 人工复核 | 字符框 / 整行框 / 复核定位 | 位置范围 x；y | 尺寸范围 宽×高 | 疑似变化 |',
                  '| --- | --- | --- | --- | --- | --- | --- |'])
    for e in summary['events']:
        change = []
        if e['suspected_movement']:
            change.append(f"中心跨度 {e['center_span_pixels']} px")
        if e['detection_box_size_changed']:
            change.append(f"框宽比 {e['width_ratio']:.2f} / 高比 {e['height_ratio']:.2f}（需画面核实）")
        lines.append(f"| {e['event_id']} / {e['link_id']} | {e['start']}–{e['end']} | "
                     f"{e['origins'].get('ocr', 0)} / {e['origins'].get('tracked', 0)} / {e['origins'].get('backfilled', 0)} / {review_count(e['origins'])} | "
                     f"{e['box_methods'].get('characters', 0)} / {e['box_methods'].get('line_fallback', 0)} / {reviewed_method_count(e['box_methods'])} | "
                     f"{e['x_range']}; {e['y_range']} | {e['width_range']} × {e['height_range']} | {'；'.join(change) or '未超过变化阈值'} |")
    lines.extend(['', '## 全局连续打码时间段', '',
                  '下表为至少一个遮挡框持续存在的时间段，多个位置的遮挡合并；切镜后若下一帧仍有框，时间连续，仍合并。', '',
                  '| 段 | 开始 | 结束（不含） | 持续秒 |', '| --- | --- | --- | --- |'])
    for i, interval in enumerate(summary['continuous_masked_intervals'], 1):
        lines.append(f"| {i} | {interval['start']} | {interval['end']} | {interval['duration_seconds']:.3f} |")
    lines.extend(['', '## 高变化审阅提示', '',
                  '这是按框变化阈值再次筛选的事件清单。即使已经做过定向复核，事件仍可能满足此阈值；本清单不表示已经证实有残留漏码。', ''])
    for e in summary['events']:
        if e['visual_review_reasons']:
            lines.append(f"- {e['event_id']}（{e['start']}–{e['end']}）：{'；'.join(e['visual_review_reasons'])}。")
    if not summary['visual_review_event_ids']:
        lines.append('未触发高变化筛选阈值；这不能证明无漏码。')
    lines.extend(['', '## 汇总阈值与验证边界', '',
                  f"- 相邻帧同 ID 匹配：框相交，或中心距离 ≤ max({summary['thresholds']['association_jump_floor_pixels']:g} px, 3 × 两框最大高度, 0.5 × 两框最大宽度)；一帧缺失即分段；切镜即分段。",
                  f"- 疑似移动：事件框中心范围对角线 > {summary['thresholds']['suspected_movement_center_span_pixels']} px；框尺寸变化：最大/最小宽或高 > {summary['thresholds']['detection_box_size_ratio']}。",
                  '- 高变化筛选：宽或高最大/最小比 > 1.25、相邻帧中心位移 > 50 px，或存在整行回退框。均为汇总筛选阈值。',
                  f"- 原处理报告验证结果：`{json.dumps(report.get('verification', {}), ensure_ascii=False)}`。这里只转录已记录的检查，不将帧数、时长或音轨检查等同于隐私遮挡完整性检查。",
                  '- 最终视觉检查记录见同目录 [视觉检查.md](视觉检查.md)。',
                  '- 时间轴 CSV 提供完整事件数据；事件摘要 JSON 包含次数、置信度范围、匹配分数、尺寸选择次数与全部连续打码区间。', ''])
    (directory / '打码汇报.md').write_text('\n'.join(lines), encoding='utf-8')
    write_review_html(summary, directory)


def write_review_html(summary, directory):
    # Embed evidence; file:// browsers must not fetch adjacent JSON.
    data = json.dumps(summary, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    document = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>前 5 分钟 · 疑似链接打码审阅</title>
<style>
:root{color-scheme:light;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#242424;background:#f4f3ef;font-size:15px}
*{box-sizing:border-box}body{margin:0}main{max-width:1600px;margin:auto;padding:28px}h1{font-size:26px;margin:0 0 10px}p{line-height:1.65;margin:8px 0}a{color:#235b72}button,input{font:inherit}button{cursor:pointer;border:1px solid #bfd1d4;border-radius:6px;padding:7px 10px;background:#eff7f8;color:#184656}button:hover{background:#dbeef1}button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid #16829a;outline-offset:3px}header{margin-bottom:22px}.muted{color:#656565}.layout{display:grid;grid-template-columns:minmax(360px,1fr) minmax(500px,1.3fr);gap:24px;align-items:start}.viewer{position:sticky;top:20px;background:white;padding:16px;border:1px solid #deded8;border-radius:10px}video{width:100%;max-height:65vh;background:#141414;border-radius:5px}#selection{font-weight:600;min-height:24px}#status{min-height:24px;font-size:13px}.controls{background:white;border:1px solid #deded8;border-radius:10px;padding:14px;margin-bottom:14px}.filters{display:flex;gap:14px;flex-wrap:wrap}.filters label{display:flex;gap:5px;align-items:center}.table-wrap{overflow:auto;max-height:75vh;border:1px solid #deded8;border-radius:8px;background:white}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}thead{position:sticky;top:0;background:#e9efed;z-index:1}th,td{text-align:left;padding:11px 10px;border-bottom:1px solid #e8e8e1}th{font-size:12px}tr.selected{background:#e2f1f2}.change{white-space:normal;min-width:180px;line-height:1.55}footer{margin-top:22px;font-size:13px}#empty{padding:20px;text-align:center}input[type=checkbox]{accent-color:#28778b}@media(max-width:1000px){main{padding:18px}.layout{grid-template-columns:1fr}.viewer{position:static}video{max-height:50vh}.table-wrap{max-height:65vh}}
</style>
</head>
<body><main>
<header><h1>前 5 分钟 · 疑似链接打码审阅</h1>
<p>点击事件会定位到其出现前 0.5 秒并播放。时间以原视频开头为 00:00；结束时刻不包含在事件内。</p>
<p class="muted">框位置变化仅表示疑似移动；<strong>框尺寸变化不证明画面缩放，需结合视频核实。</strong>自动检测仍可能漏码或误码。</p></header>
<p class="muted" id="reviewNote"></p>
<div class="layout">
<section class="viewer" aria-label="视频审阅">
<video id="video" controls preload="metadata"><source src="redacted.mp4" type="video/mp4">当前浏览器无法播放此视频，请打开同目录的 redacted.mp4。</video>
<p id="selection">尚未选择事件</p><p class="muted" id="status" role="status" aria-live="polite"></p>
<p class="muted">保持本页面与 redacted.mp4 在同一文件夹。播放器可用于回看前后帧；表格中的遮挡框次数包含同帧多个位置。</p>
<p><a href="时间轴.csv" download>时间轴 CSV</a> · <a href="打码汇报.md">完整汇报</a> · <a href="视觉检查.md">视觉检查</a> · <a href="事件摘要.json">证据 JSON</a></p>
</section>
<section aria-label="事件时间轴"><div class="controls">
<div class="filters"><label><input id="tracked" type="checkbox">有正向跟踪</label><label><input id="backfilled" type="checkbox">有回填</label><label><input id="fallback" type="checkbox">有整行回退</label><label><input id="review" type="checkbox">有人工复核修正</label><button id="reset" type="button">清除筛选</button></div>
<p class="muted" id="count"></p><p class="muted">选中多个条件时显示满足任一条件的事件。未选条件时显示全部事件。</p>
</div>
<div class="table-wrap"><table><thead><tr><th>事件 / 匿名 ID</th><th>起止时刻</th><th>OCR / 跟踪 / 回填 / 复核</th><th>字符 / 整行 / 复核定位</th><th>检测框变化</th></tr></thead><tbody id="rows"></tbody></table><div id="empty" hidden>没有符合筛选条件的事件。</div></div></section>
</div><footer class="muted">同一匿名 ID 同时处于不同位置会分别记录；切镜、消失及空间断开会分段。表格不展示识别到的真实网址或参数。</footer>
</main>
<script id="evidence" type="application/json">__EVIDENCE__</script>
<script>
"use strict";
const evidence=JSON.parse(document.getElementById("evidence").textContent);
const video=document.getElementById("video"), rows=document.getElementById("rows"), selection=document.getElementById("selection"), status=document.getElementById("status");
const filters=["tracked","backfilled","fallback","review"].map(id=>document.getElementById(id));
function reviewCount(event){return Object.entries(event.origins).filter(([key])=>key.startsWith("review_")).reduce((total,[key,value])=>total+value,0)}
function reviewedMethodCount(event){return Object.entries(event.box_methods).filter(([key])=>key.startsWith("reviewed_")).reduce((total,[key,value])=>total+value,0)}
document.getElementById("reviewNote").textContent=evidence.manual_review_region_instances?"本成片包含首轮自动识别及人工复核后的定向修正。复核局部 OCR、字形模板、模板、颜色行和时间桥接均另行计数，不代表首轮模型独立完成。":"本成片为首轮自动识别结果。";
if(evidence.repairs_evidence&&evidence.repairs_evidence.glyph_row_trim_regions){document.getElementById("reviewNote").textContent+=" 另有 "+evidence.repairs_evidence.glyph_row_trim_regions+" 次代码托管链接模板框按白字行及上下 4 px 余量收窄高度，保留橙色字幕与下一行中文。"}
let selected=null,pendingTime=null;
function cell(row,text,className){const td=document.createElement("td");td.textContent=text;if(className)td.className=className;row.append(td);return td}
function playEvent(event){
 selected=event.event_id;selection.textContent=event.event_id+" / "+event.link_id+" · "+event.start+"–"+event.end;
 pendingTime=Math.max(0,event.start_seconds-.5);status.textContent="正在定位到事件出现前 0.5 秒。";
 if(video.readyState>=1)seekAndPlay();render();
}
function seekAndPlay(){
 if(pendingTime===null)return;
 const destination=Number.isFinite(video.duration)?Math.min(pendingTime,Math.max(0,video.duration-.01)):pendingTime;
 pendingTime=null;
 try{video.currentTime=destination;const play=video.play();if(play&&typeof play.catch==="function")play.catch(()=>{status.textContent="已定位，请点击播放器播放。"});status.textContent="已定位；请核实链接是否遮住，以及遮罩是否随画面变化。"}
 catch(error){status.textContent="播放器未能定位，请直接打开同目录 redacted.mp4 核实该时间。"}
}
video.addEventListener("loadedmetadata",seekAndPlay);
video.addEventListener("error",()=>{status.textContent="视频加载失败。请确认 redacted.mp4 与本页面同目录，或直接打开视频。"});
function render(){
 const enabled=filters.filter(input=>input.checked).map(input=>input.id);
 const events=evidence.events.filter(event=>!enabled.length||enabled.some(key=>key==="review"?reviewCount(event)>0:key==="fallback"?(event.box_methods.line_fallback||0)>0:(event.origins[key]||0)>0));
 rows.replaceChildren();
 for(const event of events){
  const row=document.createElement("tr");if(event.event_id===selected)row.className="selected";
  const first=cell(row,"");const button=document.createElement("button");button.type="button";button.textContent=event.event_id+" / "+event.link_id;button.setAttribute("aria-label","播放 "+event.event_id+"，开始 "+event.start);button.addEventListener("click",()=>playEvent(event));first.append(button);
  cell(row,event.start+"\n"+event.end).style.whiteSpace="pre-line";
  cell(row,[...(["ocr","tracked","backfilled"].map(key=>event.origins[key]||0)),reviewCount(event)].join(" / "));
  cell(row,[...(["characters","line_fallback"].map(key=>event.box_methods[key]||0)),reviewedMethodCount(event)].join(" / "));
  const description="中心跨度 "+event.center_span_pixels+" px；最大相邻位移 "+event.max_center_step_pixels+" px\n宽比 "+event.width_ratio.toFixed(2)+"；高比 "+event.height_ratio.toFixed(2)+(event.detection_box_size_changed?"（框尺寸变化，需画面核实）":"");
  cell(row,description,"change").style.whiteSpace="pre-line";rows.append(row);
 }
 document.getElementById("count").textContent="显示 "+events.length+" / "+evidence.event_count+" 段事件；全部 "+evidence.region_instances+" 次遮挡框，涉及 "+evidence.masked_frames+" 帧。";
 document.getElementById("empty").hidden=events.length!==0;
}
filters.forEach(input=>input.addEventListener("change",render));
document.getElementById("reset").addEventListener("click",()=>{filters.forEach(input=>input.checked=false);render()});
render();
</script></body></html>'''
    (directory / '审阅.html').write_text(document.replace('__EVIDENCE__', data), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--jump-floor', type=float, default=160)
    parser.add_argument('--mask-area-stats', help='Reviewed frame union estimate as JSON: grid_step_pixels, median_percent, p95_percent, max_percent')
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    if report.get('status') not in (None, 'complete'):
        raise ValueError('Processing must be complete before summary generation')
    summary = summarize(report, jump_floor=args.jump_floor)
    if args.mask_area_stats:
        stats = json.loads(args.mask_area_stats)
        required = ('grid_step_pixels', 'median_percent', 'p95_percent', 'max_percent')
        if any(key not in stats or not isinstance(stats[key], (int, float)) or not math.isfinite(stats[key]) for key in required):
            raise ValueError('Invalid reviewed mask area statistics')
        if stats['grid_step_pixels'] <= 0 or not 0 <= stats['median_percent'] <= stats['p95_percent'] <= stats['max_percent'] <= 100:
            raise ValueError('Reviewed mask area statistics must be ordered percentages')
        summary['mask_area_union_estimate'] = {key: stats[key] for key in required}
    write_outputs(report, summary, args.output_dir)
    print(json.dumps({'events': summary['event_count'], 'regions': summary['region_instances'],
                      'masked_frames': summary['masked_frames'],
                      'continuous_intervals': len(summary['continuous_masked_intervals']),
                      'visual_review_events': len(summary['visual_review_event_ids'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
