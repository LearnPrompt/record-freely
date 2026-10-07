# 在公开网页复查，不必搬走整部电影

仓库：[LearnPrompt/record-freely](https://github.com/LearnPrompt/record-freely) · [Release v1.0.1](https://github.com/LearnPrompt/record-freely/releases/tag/v1.0.1) · [在线互动对比](https://learnprompt.github.io/record-freely/)

另一台电脑不需要容纳约 68.5 GB 的历史资料。公开复查从源码、证据和一分钟真实样片开始。下列地址是交付入口；上线及附件下载需以实际发布验证为准。

## 文件在哪里

| 内容 | 公开入口 | 能核实什么 |
| --- | --- | --- |
| Skill 与便携源码 | [SKILL.md](../SKILL.md)、[scripts](../scripts)、[实现说明](../references/implementation.md) | Apple Vision、链接规则、跟踪、稳框、人工修订与输入 SHA 绑定 |
| 测试与合成夹具 | [tests](../tests) | 当前 70 项代码测试；历史 144 帧真 OCR 夹具及其验收范围 |
| 同帧真实对照 | [对照目录](../assets/comparisons)、[在线滑杆](https://learnprompt.github.io/record-freely/) | 01:02、06:39、09:00 的范围选择；BEFORE 保留源片原有灰块 |
| 历史案例取证 | [public-case/index.json](../evidence/public-case/index.json) | 46 个指标输入记录的公开映射，以及历史 Python/Swift 实现；不是只剩作者结论 |
| 指标与匿名摘录 | [metrics.json](../evidence/metrics.json)、[Codex token 摘录](../evidence/codex-token-excerpts.json)、[独立复查](independent-review.md) | 耗时口径、父线程遥测与历史复查结果；不包含完整聊天或凭证 |
| 全量历史资料清单 | [full-review-file-catalog.json](../evidence/full-review-file-catalog.json)、[full-review-validation.json](../evidence/full-review-validation.json) | 本地完整归档的路径、大小、哈希与验证；不能据此宣称全部媒体已上传 |
| 一分钟实际输入 | [trial-source-00m55s-01m55s.mp4](https://github.com/LearnPrompt/record-freely/releases/download/v1.0.1/trial-source-00m55s-01m55s.mp4)、[样片记录](../evidence/trial-source.json) | 原片 00:55–01:55，60 秒、1800 帧、3840×2160、30fps；约 57.35 MiB |

完整 35 分钟原片、每一版全片和所有历史中间视频留在本机 full-review-bundle。公开源码、历史证据映射和清单支持网页审阅；重新验证全片媒体哈希需要该本地资料，不能仅凭公开清单独立重算。

## 可直接交给新 Agent 的任务

> 请从 https://github.com/LearnPrompt/record-freely 读取并取得 Skill，不以作者结论代替检查。在新目录运行测试，取得 v1.0.1 Release 的 trial-source-00m55s-01m55s.mp4，按 SKILL.md 给这一分钟真实录屏打码。只遮疑似链接，保留教学文字；独立检查移动、缩放、短暂出现、切镜、误遮和漏遮。分别交付自动初稿、必要的审阅修订、实际视频、报告、运行耗时、依赖检查与源片 SHA-256。报告自动能力和人工修订的区别。不要改原片、历史证据或作者快照；不要上传新的内容或将未知 Codex 额度补成估算。若只能看网页，明确没有实跑，返回带文件位置的代码/证据发现。

试用输出中的帧号和时间从短片 0 开始；对应原片时间需加 **55 秒**。例如短片 00:07 对应原片 01:02。不要把这次短片重新编码的音频称作历史 v3 的原 AAC 编码包复制。

## 实跑所需环境与算法

目前支持 macOS，需要 Xcode Command Line Tools、FFmpeg、Python 3、OpenCV 与 NumPy。约 57.35 MiB 是输入样片的下载量；实际运行还需要输出和 FFV1 中间片的临时磁盘空间，不能把下载量当作峰值占用。引擎调用系统 Apple Vision，**不需额外下载 YOLO 或 OCR 模型权重**，也不逐帧调用云视觉 API。OCR 字符框与离线域名规则选出链接区域；OpenCV 模板匹配处理移动和缩放；稳框按连续观测区间固定或平滑覆盖框；FFmpeg 导出新视频。详见[实现说明](../references/implementation.md)。

自动初稿默认不会把所有个人路径、邮箱或 `.html` 当网址；保留作者/Skill 名、特定路径段和指定词，需要源帧审阅及精确补丁。新 Agent 的一分钟试用结果必须来自它自己的输出，历史测试不证明此次视频零漏码。

## English / 日本語

Review the source and evidence on GitHub, then download the approximately 57.35 MiB one-minute Release input if you need a real run. The full 68.5 GB historical archive stays local. Catalogs record its contents; they do not provide all media or let a remote reviewer independently rehash unavailable files. Trial time starts at zero; add 55 seconds for the original recording. macOS is required, with native Apple Vision, OpenCV, and FFmpeg; no separate model weights are needed.

GitHub 上でソースと根拠を確認し、実行する場合だけ約 57.35 MiB の1分素材を Release から取得してください。68.5 GB の履歴資料全体はローカルに保存しています。公開一覧は全動画のダウンロードではなく、入手できないファイルのハッシュを遠隔で再計算できるわけではありません。短片の時刻に55秒を加えると元動画の時刻になります。macOS 内蔵 Apple Vision・OpenCV・FFmpeg を使い、モデル重みの別途ダウンロードは不要です。

## 已完成的一分钟独立试用

[真实试用报告](one-minute-trial.md)记录自动4分54秒、修订、验收、审阅跨度和仍然存在的漏框。报告、原始输入与各版输出随 Release 提供；完整一分钟包可选下载，网页读代码与对照无需下载它。
