---
name: record-freely
description: "Locally redact visible links in screen recordings, optionally inspect contact details, identity path prefixes and QR codes, then independently review the encoded video, speech and subtitles. Use when preparing tutorials or checking privacy before publishing; platform review is a separate evidence-based Agent workflow."
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

## 可选隐私与独立复查

用户只要求网址时，继续用默认模式；用户要连同联系方式、身份路径和二维码处理时加 `--privacy`。它检查邮箱、大陆手机号、有明确标签的电话号码、身份路径前缀和二维码。其他疑似号码、编号误识别域名、低置信度候选等留待复核。候选状态是 `mask`、`needs_review`、`keep`；它们是处理决定，不是平台违规判定。同画面空间相邻的拆分地址只列为待审，不因拼接自动遮挡。身份路径前缀缺少精确字符框时待审，避免误挡目录用途。语义上应保留哪部分，仍由 Agent 看上下文确认。报告的 `review_candidates` 不保存 OCR 原文或完整联系方式，`review_summary` 汇总状态。

```bash
python3 scripts/redact_video.py /absolute/input.mp4 \
  --output-dir /absolute/privacy-preview --privacy --start 60 --duration 20
python3 scripts/review_video.py /absolute/final.mp4 \
  --output-dir /absolute/new-review --privacy --detect-every 1
```

复扫输出 `review.json`。可加 `--redaction-report /absolute/final/report.json` 校验成片 SHA-256；refine 后用最新报告，旧报告不能证明新版成片。独立复扫最终编码文件，不把原打码报告的框当作“全部敏感内容已找到”的证据。默认逐帧；`--detect-every N` 设为大于 1 就是抽样。用 `--start`、`--duration` 限定窗口时，明确窗口外未检查。候选定位与检测失败都需要交付；无候选不是零泄漏证明。复扫只产出检查材料，不修改视频。

有已有本地 Whisper 模型和 `whisper-cli` 时，可用 `--asr-model /absolute/local-model.bin` 加入语音检查；`--subtitle /absolute/captions.srt` 可重复给出字幕来源。禁止默默下载模型或自动上传媒体；音轨未检查、没有音轨、ASR 失败须分别记录。临时转写完成检测后清理，不在匿名报告保存原文。语音和字幕结果只是提醒，不自动静音或删改字幕；每条音轨分别检查；所给 SRT 时间从源视频零点开始，窗口外不计为已检查。在 Agent 语义复查时单独核对画面、口播、字幕是否仍暴露同一内容。归一化 CFR 检查对变帧率素材可能重复或丢弃源帧，交付时说明。

## 平台发布前检查（独立 Agent 工作流）

用户提出平台发布或审核分析时，读 [发布前检查流程](docs/prepublication-review.md)，复制 [空白模板](references/platform-review-template.json) 到私有任务目录。按用户指定平台、日期和投稿场景查现行官方来源；记录核验日期、适用范围与未知项。用户主动希望多遮某类内容记在偏好中，不能写成平台规则。技术网页、工具名、文件名、普通跨平台提及均须结合语境，不硬编码成禁词。

候选扫描后，结合实际画面、完整相关语音／字幕上下文判断：保留、修改、补标识、确认权利或等待材料。记录证据与反证、官方依据与推测分别在哪。通用“不适合分享”等提示只说明观察到的结果；没有明确且可核实的原因时 `confirmed_reason` 保持 `null`，不能由零流量或一次重发推导原因，不能把反馈自动升级为规则。

发布、申诉、上传和公共案例提交仍按用户授权范围处理。私有反馈默认不公开，不能把原视频、联系方式、提示原文或未脱敏截图混入公开仓库。真实发布验证是独立状态；静态检查、本地遮挡和视觉验收不能冒充平台已接受。

## 交付与复查

审阅首次出现/消失、短闪、移动、缩放、选中高亮、画面上下缘裁切及字幕交叉处。不得从当前帧按白色/橙色恢复像素，这可能把敏感字恢复出来；这个便携入口只画灰块，需要更复杂字幕层保护时单独制作可信干净图层并人工复查。

交付视频、逐帧匿名报告、修订补丁及验证记录。说明自动与人工处理边界、未定位项、真实耗时和可验证的 Codex 用量口径。原片和源帧放入用户授权的本地复查包；公开发布前明确哪些原始媒体可以公开，勿把带身份信息的工作帧混入公开资产。

脚本将 SDR 输入归一化为恒定帧率，重新编码 H.264 和 AAC；不会承诺音频数据包与原片相同。保留原分辨率，奇数边长补齐偶数像素。HDR 需要单独确认色彩工作流。检查源文件未改动、输出帧数/时长/音轨数量、完整解码和可见效果，再称为完成。
