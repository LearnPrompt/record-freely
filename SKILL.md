---
name: record-freely
description: "Redact visible web links in local screen recordings with macOS OCR, conservative motion tracking, stable masks, and frame-reviewed corrections. Use when preparing tutorial videos or revising link masking while keeping useful content readable."
---

# 放心录 · Record Freely

让创作者先把内容录下来，再由 Agent 在本地处理疑似网址。目标是尽量小、稳定、可审阅的遮挡；不承诺平台审核结果或自动零漏码。

## 使用

在本 Skill 目录执行命令，所有输入路径用绝对路径，输出目录必须是新目录。无需联网、API Key、YOLO 或上传画面；首版需要 macOS Vision、Xcode Command Line Tools、FFmpeg，以及 Python 的 OpenCV/NumPy。

先做与用户片段相符的预览，查看源帧和遮挡后的帧，再运行全片。默认每帧 OCR、solid 灰块，保留普通文本和文件扩展名：

```bash
python3 scripts/redact_video.py /absolute/input.mp4 \
  --output-dir /absolute/preview --start 60 --duration 20
python3 scripts/redact_video.py /absolute/input.mp4 \
  --output-dir /absolute/full --ocr-workers 3
```

`report.json` 保存匿名逐帧矩形、切镜位置和原文件完整 SHA256；refine 在输出创建前核对内容哈希，拒绝同尺寸/同修改时间的无关影片。`preview.jpg` 是抽样审阅，不是全帧漏码证明。保留原输入和自动报告。完整 URL 的自动识别不等于自动理解“应该留下哪个作者/Skill 后缀”。如果用户要保留后缀、隐藏用户名路径或纠正多挡，审阅原始帧后用 SHA 绑定的人工矩形补丁；不要把所有本地文件路径一概当链接，也不要凭字符串长度猜像素边界。

需要改善抖动或套用人工修正时读 [实现与补丁格式](references/implementation.md)，再从原片重渲染：

```bash
python3 scripts/refine_video.py /absolute/input.mp4 \
  --report /absolute/full/report.json --stabilize \
  --patch /absolute/reviewed.json --output-dir /absolute/revised
```

没有人工修正就省略 `--patch`。稳框只合并连续已观测区间：静止段采用覆盖所有检测框的固定包络，移动段限制平滑后的框仍覆盖当前检测框；切镜和缺失帧断开。它不补出没有证据的帧，也不能替代漏码检查。人工矩形在稳框后应用，以保留用户确认的后缀边界。

## 交付与复查

审阅首次出现/消失、短闪、移动、缩放、选中高亮、画面上下缘裁切及字幕交叉处。不得从当前帧按白色/橙色恢复像素，这可能把敏感字恢复出来；这个便携入口只画灰块，需要更复杂字幕层保护时单独制作可信干净图层并人工复查。

交付视频、逐帧匿名报告、修订补丁及验证记录。说明自动与人工处理边界、未定位项、真实耗时和可验证的 Codex 用量口径。原片和源帧放入用户授权的本地复查包；公开发布前明确哪些原始媒体可以公开，勿把带身份信息的工作帧混入公开资产。

脚本将 SDR 输入归一化为恒定帧率，重新编码 H.264 和 AAC；不会承诺音频数据包与原片相同。保留原分辨率，奇数边长补齐偶数像素。HDR 需要单独确认色彩工作流。检查源文件未改动、输出帧数/时长/音轨数量、完整解码和可见效果，再称为完成。
