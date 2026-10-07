#!/usr/bin/env python3
"""Merge completed redaction chunks into an auditable global timeline."""
import argparse
import csv
import importlib.util
import json
import math
from collections import Counter
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
TIMELINE_SCRIPT = WORKSPACE / 'work/real-video-audit/timeline_report.py'
spec = importlib.util.spec_from_file_location('redaction_timeline', TIMELINE_SCRIPT)
timeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timeline)
ORIGIN_LABELS = dict(timeline.ORIGIN_LABELS)
ORIGIN_LABELS.update(review_url_continuation='人工复核网址续行或完整路径与参数补码',
                     review_color_continuation='人工复核颜色行中的网址续段',
                     review_boundary_glyph='人工复核字形边界补码',
                     review_yellow_proxy='人工复核黄色网址缩放与移动字形',
                     review_source_geometry='人工复核源画面网址几何',
                     review_source_template='人工复核源画面公有前缀模板',
                     review_white_proxy_gap='人工复核白字网址短缺口',
                     review_resource_geometry='人工复核资源 URI 参数行几何',
                     review_public_host_template='人工复核公有主机前缀模板',
                     reviewed_current_frame_glyph='人工复核当前帧字形',
                     review_public_host_suffix_template='人工复核公有主机后缀模板',
                     review_shell_exit='人工复核终端网址出画边缘',
                     review_shell_variant='人工复核终端网址变体',
                     review_resource_exit_tail='人工复核资源 URI 出画尾部')
METHOD_LABELS = dict(timeline.METHOD_LABELS)
METHOD_LABELS.update(reviewed_continuation_characters='续行字符几何定位',
                     reviewed_continuation_monospace='已确认等宽终端行的续段定位',
                     reviewed_color_continuation='已确认网址颜色续段定位',
                     reviewed_uri_glyphs='复核 URI 公有前缀 OCR 与当前字形范围',
                     reviewed_uri_prefix_template='复核 URI 前缀模板与当前字形范围',
                     reviewed_uri_source_prefix='复核同场景 URI 前缀局部字形模板',
                     reviewed_public_prefix_ocr='复核局部原生 OCR 的公有网址前缀与可见续段',
                     glyph_width_word='原生 OCR 词块与字形宽度定位',
                     reviewed_animation_geometry_glyph_projection='复核动画位置与字形投影',
                     reviewed_proxy_word='复核局部缩放 OCR 词块',
                     reviewed_glyph_boundary='复核字形边界',
                     reviewed_fade_glyph='复核淡入淡出字形',
                     reviewed_color_glyph='复核颜色字形',
                     reviewed_url_row='复核网址行定位',
                     reviewed_public_prefix_template='复核公有前缀模板',
                     reviewed_prefix_template='复核前缀模板',
                     reviewed_asset_argument_geometry='复核资源参数中的独立 URI 行',
                     reviewed_shell_uri_geometry='复核终端 URI 几何',
                     reviewed_visible_uri_boundary='复核当前可见 URI 边界',
                     reviewed_address_prefix_template='复核浏览器地址前缀模板',
                     reviewed_uri_tail_public_flag_anchor='复核 URI 尾部与公有参数标记定位')


def review_count(counts):
    return sum(count for key,count in counts.items() if key.startswith(('review_','reviewed_')))


def read_technical_verification(path):
    """Require an actual passing export record; a chunk report is insufficient."""
    evidence = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(evidence, dict):
        raise ValueError('Technical verification must be a JSON object')
    if evidence.get('status') in ('failed', 'error') or evidence.get('passed') is False or evidence.get('all_passed') is False:
        raise ValueError('Final technical verification records a failure')
    if not (evidence.get('status') == 'passed' or evidence.get('passed') is True or evidence.get('all_passed') is True):
        raise ValueError('Final technical verification has not explicitly passed')
    checks = evidence.get('checks', evidence.get('verification', {}))
    if not isinstance(checks, dict) or checks.get('full_video_and_audio_codec_decode') is not True:
        raise ValueError('Full movie codec decoding verification has not completed')
    flattened = {}

    def walk(value, prefix=''):
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f'{prefix}.{key}' if prefix else str(key))
        elif isinstance(value, (bool, int, float, str)):
            flattened[prefix] = value

    walk(checks)
    failed = [key for key, value in flattened.items()
              if value is False or isinstance(value, str) and value.lower() in ('failed', 'error', 'mismatch')]
    if failed:
        raise ValueError('A final technical check failed: ' + ', '.join(failed))
    # Support explicit copy flags and encoded-packet hash equality evidence.
    proof_fields = {}
    walk(evidence)
    for key, value in flattened.items():
        normalized = key.lower()
        if ('audio' in normalized or 'aac' in normalized) and ('copy' in normalized or 'hash' in normalized or 'packet' in normalized):
            proof_fields[key] = value
    audio_copy_verified = any(value is True or isinstance(value, str) and value.lower() == 'passed'
                              for value in proof_fields.values())
    if not audio_copy_verified:
        raise ValueError('Final technical verification needs explicit audio copy or encoded-packet equality evidence')
    return {'status': 'passed', 'checks': checks, 'measurements': evidence.get('measurements', evidence.get('video', {})),
            'audio_packet_count': evidence.get('audio_packet_count'),
            'audio_copy_verified': audio_copy_verified,
            'source_record_name': Path(path).name}


def merge_chunks(first_report, chunks_root, chunks_count=7, chunk_seconds=300,
                 expected_duration=2129.033333, allow_incomplete=False):
    paths = [Path(first_report)] + [Path(chunks_root) / f'part-{i:02}' / 'report.json'
                                  for i in range(1, chunks_count + 1)]
    merged = {'status': 'complete', 'frames': [], 'scene_cuts': []}
    segments = []
    fps = width = height = None
    for index, path in enumerate(paths):
        if not path.exists():
            if allow_incomplete:
                break
            raise FileNotFoundError(f'Completed chunk report missing: part-{index:02}')
        report = json.loads(path.read_text(encoding='utf-8'))
        if report.get('status') != 'complete':
            raise ValueError(f'part-{index:02}: processing has not completed')
        current_fps = float(report['fps'])
        if fps is None:
            fps, width, height = current_fps, report['width'], report['height']
            merged.update(fps=fps, width=width, height=height)
        if not math.isclose(current_fps, fps, abs_tol=1e-6) or (report['width'], report['height']) != (width, height):
            raise ValueError(f'part-{index:02}: frame rate or frame dimensions differ')
        offset = round(index * chunk_seconds * fps)
        if offset != len(merged['frames']):
            raise ValueError(f'part-{index:02}: preceding chunk length does not match global offset')
        frames = report['frames']
        if len(frames) != report['processed_frames']:
            raise ValueError(f'part-{index:02}: reported frame count differs from frame records')
        if not frames:
            raise ValueError(f'part-{index:02}: empty report')
        source_counts, method_counts = Counter(), Counter()
        for local_index, frame in enumerate(frames):
            if frame['frame'] != local_index:
                raise ValueError(f'part-{index:02}: frame records must be contiguous and start at zero')
            if len(frame['boxes']) != len(frame['regions']):
                raise ValueError(f'part-{index:02}: box and region counts differ')
            regions = []
            for region_index, region in enumerate(frame['regions']):
                # Prefix IDs even when text coincidentally matches across chunks.
                identity = region.get('id') or 'unidentified'
                origin = region.get('origin') or frame.get('origins', ['unknown'] * len(frame['boxes']))[region_index]
                regions.append(dict(region, id=f'P{index:02}:{identity}', origin=origin))
                source_counts[origin] += 1
                method_counts[region.get('box_method', 'unknown')] += 1
            merged['frames'].append({'frame': offset + local_index,
                                     'time': round((offset + local_index) / fps, 6),
                                     'boxes': frame['boxes'], 'regions': regions,
                                     'origins': [r['origin'] for r in regions]})
        for cut in report.get('scene_cuts', []):
            merged['scene_cuts'].append(offset + (int(cut['frame']) if isinstance(cut, dict) else int(cut)))
        # A chunk boundary is a reporting boundary, not a detected camera cut.
        if index:
            merged['scene_cuts'].append(offset)
        masked = sum(bool(f['boxes']) for f in frames)
        if masked != report['masked_frames']:
            raise ValueError(f'part-{index:02}: masked frame count differs from records')
        segments.append({'part': f'P{index:02}', 'start_frame': offset,
                         'end_frame_exclusive': offset + len(frames),
                         'start': timeline.stamp(offset / fps),
                         'end': timeline.stamp((offset + len(frames)) / fps),
                         'processed_frames': len(frames), 'masked_frames': masked,
                         'origin_counts': dict(source_counts), 'box_method_counts': dict(method_counts),
                         'manual_review_region_instances': review_count(source_counts),
                         'verification': report.get('verification', {}),
                         'configuration': {k: report[k] for k in ('engine', 'style', 'padding', 'detect_every',
                                                                'hold_seconds', 'lookback_frames', 'ocr_workers',
                                                                'tld_snapshot') if k in report},
                         'repairs': {k: report.get('repairs', {})[k] for k in
                                     ('false_positive_regions_removed', 'reviewed_regions_added', 'glyph_row_trim_regions')
                                     if k in report.get('repairs', {})}})
        del report
    if not segments:
        raise ValueError('No completed segments available')
    expected_frames = round(expected_duration * fps)
    complete = len(segments) == chunks_count + 1 and len(merged['frames']) == expected_frames
    if not complete and not allow_incomplete:
        raise ValueError(f'Incomplete full timeline: {len(merged["frames"])} / {expected_frames} frames')
    merged['scene_cuts'] = sorted(set(merged['scene_cuts']))
    merged.update(duration=len(merged['frames']) / fps, processed_frames=len(merged['frames']))
    return merged, segments, complete, expected_frames


def activity_windows(summary, join_gap_seconds=2):
    windows = []
    fps = summary['fps']
    for interval in summary['continuous_masked_intervals']:
        start, end = interval['first_frame'], interval['last_frame'] + 1
        active_frames = end - start
        if windows and start - windows[-1]['end_frame_exclusive'] <= round(join_gap_seconds * fps):
            windows[-1]['end_frame_exclusive'] = end
            windows[-1]['active_frames'] += active_frames
            windows[-1]['continuous_interval_count'] += 1
        else:
            windows.append({'start_frame': start, 'end_frame_exclusive': end, 'active_frames': active_frames,
                            'continuous_interval_count': 1})
    for window in windows:
        window['start'] = timeline.stamp(window['start_frame'] / fps)
        window['end'] = timeline.stamp(window['end_frame_exclusive'] / fps)
        window['active_seconds'] = round(window['active_frames'] / fps, 6)
    return windows


def write_csv(summary, output):
    origin_keys = list(ORIGIN_LABELS)
    origin_keys += sorted(set(summary['origin_counts']) - set(origin_keys))
    method_keys = list(METHOD_LABELS)
    method_keys += sorted(set(summary['box_method_counts']) - set(method_keys))
    with output.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['事件', '分段', '匿名候选_复核标识', '原视频开始时间', '原视频结束时间_不含',
                         '开始帧', '结束帧_不含', '框次数'] + origin_keys + method_keys +
                        ['x范围_px', 'y范围_px', '宽范围_px', '高范围_px', '中心跨度_px', '最大相邻位移_px',
                         '框宽比', '框高比', '模板尺寸选择次数', '高变化提示'])
        for event in summary['events']:
            writer.writerow([event['event_id'], event['link_id'].split(':', 1)[0], event['link_id'],
                             event['start'], event['end'], event['first_frame'], event['last_frame'] + 1,
                             event['box_count']] + [event['origins'].get(k, 0) for k in origin_keys] +
                            [event['box_methods'].get(k, 0) for k in method_keys] +
                            [event['x_range'], event['y_range'], event['width_range'], event['height_range'],
                             event['center_span_pixels'], event['max_center_step_pixels'], event['width_ratio'],
                             event['height_ratio'], json.dumps(event['relative_scale_counts']),
                             '；'.join(event['visual_review_reasons'])])


def report_markdown(summary):
    frames, fps, total = summary['processed_frames'], summary['fps'], summary['region_instances']
    duration = timeline.stamp(frames / fps)
    lines = ['# 《带封面》完整版打码汇报', '',
             f"原片实际时长 {timeline.stamp(summary['expected_full_video_frames'] / fps)}，并非此前估计的 30 分钟。前 5 分钟沿用已批准成片，其余 {timeline.stamp(max(0, summary['expected_full_video_frames'] - summary['segments'][0]['processed_frames']) / fps)} 接续处理并拼接。",
             f"覆盖原视频 00:00:00.000–{duration}，共 {frames} 帧；时间轴均为原视频全局时间，结束时刻不包含在区间内。",
             f"有遮挡 {summary['masked_frames']} 帧，合计 {summary['masked_duration_seconds']:.3f} 秒；产生 {total} 次框和 {summary['event_count']} 段事件。",
             f"共 {summary['anonymous_candidate_id_count']} 个匿名候选/复核标识，包含 OCR 变体与人工补框标签，不等同真实网址数。每个分段的标识增加 P00/P01 等前缀，以免同名标识误合并。", '',
             '**复核范围：**前 5 分钟沿用已完成的人工复核与观看微调记录。后续分段按其各自报告统计自动识别和实际复核来源；本汇报不表示全片经过人眼逐帧检查。自动筛选和抽看仍可能漏码或误码。', '']
    if not summary['full_video_complete']:
        lines.extend(['**当前为未完成的分段预览汇报，尚未覆盖原视频全部时长。**', ''])
    lines.extend(['## 分段场景、方法与验证', '',
                  '场景描述采用检测证据：网址/域名文字、前 5 分钟已确认的模板/字幕片段。后续分段的自动检测次数不证明每个候选都是真实链接。', '',
                  '| 原视频范围 | 分段 | 框次数 / 有框帧 | 实际处理 | 分段记录验证 |', '| --- | --- | --- | --- | --- |'])
    for segment in summary['segments']:
        count = sum(segment['origin_counts'].values())
        review = segment['manual_review_region_instances']
        kinds = '网址/域名文字：逐帧 OCR + 模板跟踪及回填'
        if segment['part'] == 'P00':
            kinds = '代码托管/分享网址、models.dev、字幕和长蓝链接；沿用原自动识别与复核修正'
        if review:
            kinds += f'；人工复核来源 {review} 次框'
        verification = '；'.join(f'{k}={v}' for k, v in segment['verification'].items()) or '未记录'
        lines.append(f"| {segment['start']}–{segment['end']} | {segment['part']} | {count} / {segment['masked_frames']} | {kinds} | {verification} |")
    lines.extend(['', '分段记录中的帧数、时长和音轨检查只说明该段的导出一致性。最终成片技术验证与采样视觉检查分开记录；本脚本读取已完成的验证结果，实际视觉记录见 [视觉检查.md](视觉检查.md)。', ''])
    technical = summary.get('technical_verification')
    if technical:
        lines.extend(['## 最终成片技术验证', '',
                      f"已读取技术验证记录 `{technical['source_record_name']}`，其最终状态为 passed；只有记录实际通过后才写入本汇报。",
                      '原始 AAC 音轨采用全片直接 copy；技术记录已确认音频拷贝或编码包一致性。此结果不由分段音轨检查推断。', '',
                      '| 实际检查项 | 记录结果 |', '| --- | --- |'])
        for key, value in technical['checks'].items():
            result = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
            lines.append(f'| {key} | {result.replace("|", "/")} |')
        lines.append('')
    lines.extend([
                  '## 主要活跃区间', '',
                  '将相隔不超过 2 秒的连续打码段合为一个审阅窗口；窗口中的间隙并非都有遮罩。主文最多列出按实际有框时长排序的前 30 个窗口，全部连续区间保存在事件摘要 JSON，全部事件保存在 CSV 与审阅页。', '',
                  '| 原视频窗口 | 候选/片段类别 | 实际处理 | 实际有框秒数 | 连续段数 |', '| --- | --- | --- | --- | --- |'])
    selected = sorted(summary['activity_windows'], key=lambda window: window['active_frames'], reverse=True)[:30]
    for window in sorted(selected, key=lambda item: item['start_frame']):
        events=[event for event in summary['events'] if event['first_frame']<window['end_frame_exclusive']
                and event['last_frame']+1>window['start_frame']]
        origins=Counter();kinds=Counter()
        for event in events:
            origins.update(event['origins']);kinds.update(event['kinds'])
        categories=[]
        if kinds.get('http(s)') or kinds.get('www'):categories.append('显式网址文字')
        if kinds.get('domain'):categories.append('裸域名候选')
        if any(event['link_id'].split(':')[-1].startswith(('CU03','CU04','CAG','CAT','CAN_','CTF_')) for event in events):
            categories.append('含复核飞书文档/任务 URI')
        used=[]
        for key,label in [('ocr','逐帧原生 OCR'),('tracked','当前帧模板跟踪'),('backfilled','匹配缓存回填')]:
            if origins.get(key):used.append(label)
        if any(key.startswith(('review_','reviewed_')) for key in origins):used.append('人工复核补码')
        lines.append(f"| {window['start']}–{window['end']} | {'、'.join(categories) or '网址候选/复核片段'} | {'、'.join(used)} | {window['active_seconds']:.3f} | {window['continuous_interval_count']} |")
    lines.extend(['', '## 实际方法占比', '', '| 框来源 | 次数 | 全部框占比 |', '| --- | --- | --- |'])
    for key, count in summary['origin_counts'].items():
        lines.append(f"| {ORIGIN_LABELS.get(key, key)} | {count} | {100*count/total:.3f}% |" if total else f'| {key} | 0 | 0% |')
    lines.extend(['', '| 框定位方法 | 次数 | 全部框占比 |', '| --- | --- | --- |'])
    for key, count in summary['box_method_counts'].items():
        lines.append(f"| {METHOD_LABELS.get(key, key)} | {count} | {100*count/total:.3f}% |" if total else f'| {key} | 0 | 0% |')
    lines.extend(['', '分母为遮挡框次数，同一帧可能有多个框；这些比例不是视频时长或遮罩面积。', '',
                  '## 移动、缩放和字幕处理', '',
                  '本地原生 OCR 逐帧更新文字位置和尺寸。OCR 临时缺失时，在上一框周围 70 px 内以 1.00、0.94、1.06 倍模板匹配，分数至少 0.87 才补漏；跟踪依赖当前帧匹配证据，按实际移动更新位置，不盲目固定保留上一次的框。向前缓存回填同样要求视觉匹配，切镜重置。各段实际配置见事件摘要 JSON。', '',
                  '前 5 分钟的快速缩放、字幕交叠、局部站点字样和长蓝链接尾部沿用人工复核模板、局部 OCR、字形模板、颜色行和短时间桥接。168 次代码托管链接模板框按白字行及上下 4 px 余量收窄，保留橙色字幕与下一行中文。此人工处理不能推广为后续分段的自动能力。', '',
                  '后续人工复核补码按实际来源单列。已确认代码网址列表中，上行含未闭合的 quoted HTTP 字符串并贴近右边界，才补相邻终端续行至闭合引号前；普通文件行、后续代码和 Skill 标签保留。已确认飞书文档/任务 URI 则使用原生 OCR 的公有前缀、同场景前缀局部字形模板及当前帧可见字形范围，补齐原检测框外的路径或参数尾部；顶端裁切和章节叠层通过实际可见字形定位处理。这两种修正均归 review_url_continuation，不能混写为全片自动能力。review_color_continuation 表示已确认网址颜色行的续段补码。', '',
                  '特定叠层保护只用于已确认片段：前 5 分钟的橙色字幕，以及后续已复核黄色 URI 与白字幕交叠区域；这不是全片自动字幕分离。21:53.533–21:54.367 的飞书任务 URI 与顶部章节导航重合，为完整遮住可见 URI 使用窄灰条，约 0.833 秒内也遮住第 2 章节标题的重合文字；未恢复可能同时暴露浅绿 URI 的白色像素。结束取原片实际出画帧，而非旧 OCR 候选终点。', '',
                  '框尺寸变化可能来自 OCR 抖动或定位方式改变，不能据此确认真实镜头放大或缩小。框中心跨度与宽高比例保存在 CSV/审阅页；模板尺寸选择按来源细分保存在 JSON，不把复核模板当作自动跟踪。', '',
                  '## 审阅与限制', '',
                  '- [审阅.html](审阅.html)：按分段、方法与高变化筛选，点击事件定位其出现前 0.5 秒。',
                  '- [时间轴.csv](时间轴.csv)：全部事件的精确起止、来源次数、位置、尺寸与变化指标。',
                  '- [事件摘要.json](事件摘要.json)：全部事件、连续打码段、活跃窗口、分段配置与验证证据。',
                  '- 报告只展示匿名标识与公有域名类别，隐藏私有网址全文及参数。',
                  '- 置信度、框数、时长或音轨检查不能证明零漏码。高变化提示是复看入口，不等于已确认的漏码。', ''])
    return '\n'.join(lines)


def review_html(summary):
    compact = {'events': [{key: event[key] for key in
                          ('event_id', 'link_id', 'start', 'end', 'start_seconds', 'origins', 'box_methods',
                           'center_span_pixels', 'max_center_step_pixels', 'width_ratio', 'height_ratio',
                           'visual_review_reasons')} for event in summary['events']],
               'segments': [s['part'] for s in summary['segments']],
               'processed_frames': summary['processed_frames'], 'masked_frames': summary['masked_frames'],
               'region_instances': summary['region_instances']}
    data = json.dumps(compact, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    return r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>完整版 · 链接打码审阅</title><style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#242424;background:#f4f3ef;font-size:15px}*{box-sizing:border-box}body{margin:0}main{max-width:1600px;margin:auto;padding:25px}h1{font-size:26px;margin:0 0 12px}p{line-height:1.6}.muted{color:#606060}.layout{display:grid;grid-template-columns:minmax(360px,1fr) minmax(600px,1.4fr);gap:22px;align-items:start}.viewer{position:sticky;top:20px;background:white;padding:15px;border:1px solid #deded8;border-radius:8px}video{width:100%;max-height:65vh;background:#151515}.controls{background:white;border:1px solid #deded8;border-radius:8px;padding:13px;margin-bottom:12px}.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:center}button,input,select{font:inherit}button,select,input[type=search]{padding:7px 10px;border:1px solid #c2d0d3;border-radius:5px}button{cursor:pointer;background:#eff7f8;color:#184656}button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #16829a;outline-offset:3px}input[type=checkbox]{accent-color:#28778b}.table-wrap{overflow:auto;max-height:68vh;background:white;border:1px solid #deded8;border-radius:8px}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}thead{position:sticky;top:0;background:#e9efed;z-index:1}th,td{text-align:left;padding:10px;border-bottom:1px solid #e6e6df}td.change{white-space:pre-line;min-width:170px}.selected{background:#e1f0f2}.pagination{display:flex;gap:12px;align-items:center;padding:12px 0}a{color:#235b72}#status{min-height:24px}#empty{text-align:center;padding:20px}@media(max-width:1100px){main{padding:15px}.layout{grid-template-columns:1fr}.viewer{position:static}video{max-height:50vh}}
</style></head><body><main><h1>完整版 · 链接打码审阅</h1><p>时间为原视频全局时间。点击事件从出现前 0.5 秒播放，结束时刻不包含在区间内。每页显示 100 段事件。</p><p class="muted">前 5 分钟沿用人工复核修正；后续分段按实际记录显示来源。此页面不证明全片经过人眼逐帧检查。框尺寸变化不证明真实画面缩放，需结合视频核实。</p><div class="layout"><section class="viewer"><video id="video" controls preload="metadata"><source src="redacted.mp4" type="video/mp4">请打开同目录的 redacted.mp4。</video><p id="selection">尚未选择事件</p><p id="status" class="muted" role="status" aria-live="polite"></p><p><a href="打码汇报.md">汇报</a> · <a href="时间轴.csv" download>完整时间轴 CSV</a> · <a href="视觉检查.md">视觉检查</a> · <a href="事件摘要.json">证据 JSON</a></p></section><section><div class="controls"><div class="filters"><label>分段 <select id="part"><option value="">全部</option></select></label><input id="search" type="search" placeholder="事件、标识或时间" aria-label="搜索事件、标识或时间"><label><input id="tracked" type="checkbox">有跟踪</label><label><input id="backfilled" type="checkbox">有回填</label><label><input id="review" type="checkbox">有人工复核</label><label><input id="fallback" type="checkbox">整行回退</label><label><input id="changed" type="checkbox">高变化</label><button id="reset" type="button">清除筛选</button></div><p id="count" class="muted"></p><p class="muted">多个方法勾选按满足任一条件筛选；分段和搜索与方法条件同时生效。</p></div><div class="table-wrap"><table><thead><tr><th>事件 / 标识</th><th>原视频起止</th><th>OCR / 跟踪 / 回填 / 复核</th><th>框变化</th></tr></thead><tbody id="rows"></tbody></table><div id="empty" hidden>没有符合条件的事件。</div></div><div class="pagination"><button id="previous" type="button">上一页</button><span id="page"></span><button id="next" type="button">下一页</button></div></section></div></main><script id="evidence" type="application/json">__DATA__</script><script>
"use strict";
const data=JSON.parse(document.getElementById("evidence").textContent),rows=document.getElementById("rows"),video=document.getElementById("video"),part=document.getElementById("part"),search=document.getElementById("search"),status=document.getElementById("status");
const filters=["tracked","backfilled","review","fallback","changed"].map(id=>document.getElementById(id));let page=0,selected=null,pending=null,matching=[];
for(const name of data.segments){const option=document.createElement("option");option.value=name;option.textContent=name;part.append(option)}
function reviews(e){return Object.entries(e.origins).filter(([k])=>k.startsWith("review_")||k.startsWith("reviewed_")).reduce((n,[k,v])=>n+v,0)}
function qualifies(e,key){return key==="review"?reviews(e)>0:key==="changed"?e.visual_review_reasons.length>0:key==="fallback"?(e.box_methods.line_fallback||0)>0:(e.origins[key]||0)>0}
function cell(row,text,kind){const td=document.createElement("td");td.textContent=text;if(kind)td.className=kind;row.append(td);return td}
function filter(){const methods=filters.filter(x=>x.checked).map(x=>x.id),query=search.value.trim().toLowerCase();matching=data.events.filter(e=>(!part.value||e.link_id.startsWith(part.value+":"))&&(!query||(e.event_id+" "+e.link_id+" "+e.start+" "+e.end).toLowerCase().includes(query))&&(!methods.length||methods.some(k=>qualifies(e,k))));page=0;render()}
function render(){rows.replaceChildren();const pages=Math.max(1,Math.ceil(matching.length/100));page=Math.max(0,Math.min(page,pages-1));for(const e of matching.slice(page*100,page*100+100)){const row=document.createElement("tr");if(e.event_id===selected)row.className="selected";const first=cell(row,"");const button=document.createElement("button");button.type="button";button.textContent=e.event_id+" / "+e.link_id;button.addEventListener("click",()=>choose(e));first.append(button);cell(row,e.start+"\n"+e.end).style.whiteSpace="pre-line";cell(row,[e.origins.ocr||0,e.origins.tracked||0,e.origins.backfilled||0,reviews(e)].join(" / "));cell(row,"中心跨度 "+e.center_span_pixels+" px\n最大相邻位移 "+e.max_center_step_pixels+" px\n宽比 "+e.width_ratio.toFixed(2)+" / 高比 "+e.height_ratio.toFixed(2),"change");rows.append(row)}document.getElementById("count").textContent="符合筛选 "+matching.length+" / 全部 "+data.events.length+" 段；全部框 "+data.region_instances+" 次，有框 "+data.masked_frames+" / "+data.processed_frames+" 帧。";document.getElementById("page").textContent=(page+1)+" / "+pages;document.getElementById("previous").disabled=page===0;document.getElementById("next").disabled=page>=pages-1;document.getElementById("empty").hidden=matching.length!==0}
function choose(e){selected=e.event_id;pending=Math.max(0,e.start_seconds-.5);document.getElementById("selection").textContent=e.event_id+" / "+e.link_id+" · "+e.start+"–"+e.end;status.textContent="正在定位。";if(video.readyState>=1)seek();render()}
function seek(){if(pending===null)return;const position=Number.isFinite(video.duration)?Math.min(pending,Math.max(0,video.duration-.01)):pending;pending=null;try{video.currentTime=position;const playing=video.play();status.textContent="已定位，请核实遮挡范围和画面变化。";if(playing&&playing.catch)playing.catch(()=>{status.textContent="已定位，请点击播放器播放。"})}catch(error){status.textContent="定位失败，请直接打开 redacted.mp4 核实该时刻。"}}
video.addEventListener("loadedmetadata",seek);video.addEventListener("error",()=>{status.textContent="请确认 redacted.mp4 与本页面同目录，或直接打开视频。"});part.addEventListener("change",filter);search.addEventListener("input",filter);filters.forEach(x=>x.addEventListener("change",filter));document.getElementById("reset").addEventListener("click",()=>{part.value="";search.value="";filters.forEach(x=>x.checked=false);filter()});document.getElementById("previous").addEventListener("click",()=>{page--;render()});document.getElementById("next").addEventListener("click",()=>{page++;render()});filter();
</script></body></html>'''.replace('__DATA__', data)


def write_reports(merged, segments, complete, expected_frames, output_dir, technical_verification=None):
    if complete and technical_verification is None:
        raise ValueError('Final report requires the passing final technical verification JSON')
    summary = timeline.summarize(merged)
    summary['manual_review_region_instances']=review_count(summary['origin_counts'])
    summary.update(segments=segments, full_video_complete=complete,
                   expected_full_video_frames=expected_frames,
                   time_reference='Original video global time; end exclusive',
                   verification_scope=('Passing final export verification plus per-chunk evidence; visual QA is sampled'
                                       if technical_verification else 'Per-chunk evidence only; final verification not yet supplied'),
                   technical_verification=technical_verification)
    summary['activity_windows'] = activity_windows(summary)
    first_ids = {e['link_id'] for e in summary['events'] if e['link_id'].startswith('P00:')}
    removed_ids = {'P00:U012', 'P00:U015', 'P00:U083', 'P00:U133'}
    if first_ids & removed_ids:
        raise ValueError('First five-minute report still contains removed false positives')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / '事件摘要.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    write_csv(summary, output_dir / '时间轴.csv')
    (output_dir / '打码汇报.md').write_text(report_markdown(summary), encoding='utf-8')
    (output_dir / '审阅.html').write_text(review_html(summary), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-report', type=Path, default=WORKSPACE / 'outputs/带封面-前5分钟/report.json')
    parser.add_argument('--chunks-root', type=Path, default=WORKSPACE / 'work/full-video/chunks')
    parser.add_argument('--output-dir', type=Path, default=WORKSPACE / 'outputs/带封面-完整版')
    parser.add_argument('--chunks-count', type=int, default=7)
    parser.add_argument('--chunk-seconds', type=float, default=300)
    parser.add_argument('--expected-duration', type=float, default=2129.033333)
    parser.add_argument('--allow-incomplete', action='store_true', help='Explicitly produce a labelled incomplete preview')
    parser.add_argument('--technical-verification', type=Path, help='Actual passed final export verification JSON, including audio copy evidence')
    args = parser.parse_args()
    merged, segments, complete, expected = merge_chunks(args.first_report, args.chunks_root,
                                                       args.chunks_count, args.chunk_seconds,
                                                       args.expected_duration, args.allow_incomplete)
    technical = read_technical_verification(args.technical_verification) if args.technical_verification else None
    summary = write_reports(merged, segments, complete, expected, args.output_dir, technical)
    print(json.dumps({'complete': complete, 'processed_frames': summary['processed_frames'],
                      'masked_frames': summary['masked_frames'], 'events': summary['event_count'],
                      'regions': summary['region_instances'], 'segments': len(segments)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
