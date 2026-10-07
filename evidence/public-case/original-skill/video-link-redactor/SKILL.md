---
name: video-link-redactor
description: 在 macOS 本地识别视频里看起来像网址的文字，跟踪移动位置并用小范围遮罩打码，输出成片和检查预览。适用于录屏、教程和移动链接的脱敏；不检测隐藏超链接，也不默认遮挡所有文字。
---

# 视频链接自动打码

使用本机 Vision OCR 找网址文字，用 OpenCV 跟踪移动位置。默认逐帧扫描、灰色实色遮罩、文字框外加 4 像素。不需要云端模型、API 密钥或 YOLO 权重。此首版需要 macOS、Xcode Command Line Tools、FFmpeg、Python 的 opencv-python 和 numpy；不要为此修改全局 Python。缺依赖时使用已有运行环境或在任务 work/ 中创建独立虚拟环境。

## 运行

先定位用户提供的真实视频。未给视频时只能测试合成素材，不能声称真实素材已经处理。输入源文件不改动；输出目录必须是新目录，避免覆盖。

```bash
python3 /Users/carl/.codex/skills/video-link-redactor/scripts/redact_video.py "/absolute/input.mp4" --output-dir "/absolute/outputs/link-redacted-run1"
```

长视频或新类型素材可先加 `--start 0 --duration 10` 做短预览，再处理全部。使用同一脚本所在的 Python，路径含空格时正确引用。

- `--ocr-workers 3` 可启用三个本地 Vision worker。各有独立图像/进程，按原帧序输出；仍扫描每一帧。默认 1。
- `--padding 4` 控制文字周围余量，根据真实分辨率、OCR 框和露字情况调整。不要为追求小范围缩到露字。
- 默认 `--detect-every 1`，每帧 OCR。提高到 2、3 会更快，但可能漏掉短暂闪现链接；只有用户接受该取舍时才用。
- `--hold-seconds .35`：OCR 短暂失败时，只在当前帧仍有图像匹配证据的情况下跟踪，并向前回查这一小段；切镜后清空轨迹。
- `--style solid` 默认推荐。`pixelate` 仅提供视觉马赛克效果，不保证文字不可推断。

输出：`redacted.mp4`、带区域边框的 `preview.jpg`、逐帧区域和验证信息 `report.json`、运行阶段 `progress.json`。逐帧记录提供匿名网址编号、识别类型、字符框/整行回退、OCR/跟踪/回填来源与匹配分数，可据此汇总具体时间轴。报告不保存 OCR 文本或网址内容。检查预览从打码后的画面生成。处理中失败时 `report.json` 标记 failed，不能把中间文件当成成片。

## 检查与交付

确认输出帧数、时长和音轨数量；脚本会检查帧数和音轨数量，但这些检查不能代替观看。重点查看链接刚出现/刚消失、滚动、缩放、切镜、短暂闪现和文字邻接的位置。检查正常文字是否被误遮，遮罩是否露字、跳动或残留。导出的是 CFR H.264/AAC，旋转由 FFmpeg 处理，原始元数据清除；首版拒绝已标记的 HDR 输入，VFR 会转为恒定帧率。报告中区分合成测试与用户视频的实际效果。

匹配 http(s)、www、裸域名和路径，兼容域名点号附近空格。裸域名使用 bundled `scripts/iana-tlds.txt` 离线名单筛选，并要求 OCR 置信度至少 0.5；这份名单来源于 [IANA](https://data.iana.org/TLD/tlds-alpha-by-domain.txt)，处理视频时不联网。常见本地文件扩展名和邮箱不作为裸域名打码。这里只识别视觉上像网址的文字，并不验证网址真实可访问。字体小、运动模糊、严重压缩、未知域名、跨行路径、只显示“点击这里”的隐藏超链接仍可能漏识别。OCR 框是估计值，首次真实素材必须视觉检查。不要承诺零漏码。JEV/其他视觉模型接口和用途未确认前，先使用本地流程，不自动上传帧。

## 维护验证

```bash
python3 -m pytest /Users/carl/.codex/skills/video-link-redactor/scripts/test_redact_video.py -q
python3 /Users/carl/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/carl/.codex/skills/video-link-redactor
```

修改识别/跟踪后重新跑带真实运动的合成视频，检验逐帧链接覆盖、普通文字误遮、切镜后残留及音轨。不能仅凭 regex 单元测试声称视频打码有效。
