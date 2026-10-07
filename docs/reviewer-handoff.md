# 给另一位 Agent 的复查任务

另一台电脑优先使用[公开轻量复查](public-review.md)：网页读源码与证据，必要时只下载约 57.35 MiB 的一分钟样片，不必接收 68.5 GB。以下完整资料任务适用于能够访问本机归档的复查者，不能将公开文件清单当作媒体本体。

## 可直接转交的提示词

请在独立临时输出目录复查 `record-freely`，不要采用作者的验收结论作为答案。读取本包 SKILL.md、三语 README、ABOUT、脚本、测试和指标来源；完整源片、所有中间文件与各版本成片在同级 `full-review-bundle/`。你有权读这些文件和运行本地测试，不发布、不上传原视频、不改动输入快照。

1. 核对全文件目录和 SHA-256，确认完整复查包实际带了原视频与 work/、outputs/，不是只给原机器绝对路径。指标里的原工作区相对路径，应在复查包 `workspace/` 下定位。
2. 从源码在新目录复跑合成夹具，测试真 OCR、移动、三帧短闪、切镜、普通文字误遮、稳框和人工补丁。不要只验证 SKILL frontmatter 或 regex。
3. 任取一个原片区间，独立取准确 CFR 帧，检查源/v3 与公开对照资产内容一致；重点看 01:02、06:39、09:00、对应首尾与缩放，检查导航遮挡与鼠标高亮。完整视频技术证据已有，检查其方法；需要复跑时使用复查包原实现，不执行任何外部发布动作。
4. 审核自动能力与一次性案例修补的区别。便携 Skill 不自动理解作者后缀/身份路径，不包含本案例复杂章节图层/GOP 修改；不要把人工确认成果宣传为全自动。新引擎 AAC 重新编码，与 v3 案例复制原 AAC 的指标分开。
5. 审核“13分56秒处理5分钟4K”的具体范围；Codex token 缓存、父/子线程、账单额度、并行任务时间与墙钟时间分别核查。有疑点报出，不把未知额度或节省量补成估值。
6. 检查中英日故事、名称、About、影视飓风相关案例是否准确易懂；不声称官方合作、保证过审、零漏码、零 Codex 额度，或未经实测就宣称新试用通过。公开状态以仓库与 Release 实际可用结果为准。旧 25:41 的 `.html` 仍是未定位项。
7. 返回发现、严重度、对应文件/行号或帧号、可复现步骤和最小修正。若修改，只在授权的候选包内改；重跑相关检查，再核对真实可观察输出。

## 完整文件定位

正式包 `record-freely/` 可以安装并从源码运行；`full-review-bundle/` 是复查数据集。包含：

| 目录 | 实际内容 |
| --- | --- |
| `source/带封面.mp4` | 输入原视频完整文件 |
| `workspace/work/` | 本次原工作区全部中间脚本、图片、日志、JSON、分段视频、补丁备份与测试素材 |
| `workspace/outputs/` | 前5分钟、完整初版、v2、v3 的实际视频和完整报告 |
| `original-skill/video-link-redactor/` | 起点 Skill 的源代码、Swift、TLD 快照与测试 |
| `formal-skill/record-freely/` | 本轮正式包最终快照 |
| `FILE_CATALOG.json` | 所有快照文件的相对路径、字节数、SHA-256 与原来源映射 |
| `BUNDLE_VALIDATION.json` | 与输入逐文件比对、哈希、源媒体和最终视频是否完整的验证结果 |

快照目录内不依赖原 `/Users/carl/...` 路径的 symlink。案例原脚本可能仍写着历史绝对路径；它们是取证源码，不能直接执行后宣称可移植。便携新脚本在正式 Skill 中。重新运行案例脚本时将输入/输出改到复查目录，并保护历史快照。

## 公开发布与本地复查

对照帧的 BEFORE 按作者本次要求展示输入文字，源片原有灰块也保留，未伪造无灰块对照。完整复查包含原视频与身份路径，按用户授权用于本地 Agent 复查。公开入口是 [LearnPrompt/record-freely](https://github.com/LearnPrompt/record-freely) 与 [v1.0.0 Release](https://github.com/LearnPrompt/record-freely/releases/tag/v1.0.0)。完整数据集清单和本地验证记录见 [full-review-file-catalog.json](../evidence/full-review-file-catalog.json) 与 [full-review-validation.json](../evidence/full-review-validation.json)；46 个指标来源和历史实现映射见 [public-case/index.json](../evidence/public-case/index.json)。历史全量媒体留在本机，不宣称已公开上传，也不要求远端机器下载。新一分钟试用需另看实际输出和报告。

## 指标复核

`evidence/metrics.json` 保存记录哈希、时间、口径与父线程 token 的抽取行号；公开资料不包含原始聊天日志/账户 ID/凭证。另一个 Agent 若需要复核原始 token 日志，可在用户授权的同一机器读本线程日志，不能将全会话直接公开。已有 token 快照采于包装进行中，不是包装最终总消耗。
