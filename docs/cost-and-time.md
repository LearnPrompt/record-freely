# 耗时与 Codex 额度：我们实际知道多少

这个案例的完整素材是 **35 分 29.033 秒、4K、30 fps，共 63,871 帧**。发布材料可以说「5 分钟 4K 素材的首轮自动扫描与导出用时 13 分 56 秒」，不能说「35 分钟终稿几十分钟做完」。这次还有 Agent 复核、针对录屏叠层的人工判断、多轮局部修补，以及合并后的全片验证。

所有数值和原始记录位置见 [metrics.json](../evidence/metrics.json)。公开取证副本与原工作区路径的映射见 [public-case/index.json](../evidence/public-case/index.json)；另一台电脑可复核这些记录，不必下载历史全片。新增一分钟试用的计时应另列实际报告，不能套用本表。下文的 `work/...`、`outputs/...` 是原始工作区内的证据位置，完整本地审计包应保留对应文件；这些记录不是计费凭证。

## 可公开使用的速度数据

| 处理范围 | 素材长度 | 首轮本地处理时间 | 原始证据 |
| --- | --- | --- | --- |
| 首 5 分钟 | 5:00 / 9,000 帧 | 836.08 秒（13 分 56 秒） | `outputs/带封面-前5分钟/report.json` |
| part-01 | 300.000 秒 / 9,000 帧 | 967.28 秒（约 16 分 7 秒） | `work/full-video/chunks/part-01/complete.json` |
| part-02 | 300.000 秒 / 9,000 帧 | 1244.88 秒（约 20 分 45 秒） | `work/full-video/chunks/part-02/complete.json` |
| part-03 | 300.000 秒 / 9,000 帧 | 1119.05 秒（约 18 分 39 秒） | `work/full-video/chunks/part-03/complete.json` |
| part-04 | 300.000 秒 / 9,000 帧 | 1463.65 秒（约 24 分 24 秒） | `work/full-video/chunks/part-04/complete.json` |
| part-05 | 300.000 秒 / 9,000 帧 | 1582.08 秒（约 26 分 22 秒） | `work/full-video/chunks/part-05/complete.json` |
| part-06 | 300.000 秒 / 9,000 帧 | 1450.79 秒（约 24 分 11 秒） | `work/full-video/chunks/part-06/complete.json` |
| part-07 | 29.033 秒 / 871 帧 | 377.28 秒（约 6 分 17 秒） | `work/full-video/chunks/part-07/complete.json` |

后续分段由两个进程交错处理，每个进程内部再使用 2 或 3 个本地 Vision worker。各段 `elapsed_seconds` 记录该段的解码、逐帧 OCR、跟踪、编码及脚本检查；`complete.json` 的计时比 `report.json` 多包含报告收尾。后续的 `review_repairs` 计数加入了报告，但**没有把人工复核时间补进初始 elapsed 数值**。

- 后续 7 段处理时间相加是 **8205.01 秒**；这是各任务时间之和，因进程交错运行，不能当作墙钟时间。
- 包括首 5 分钟，首轮任务时间之和是 **9041.09 秒**；同样不表示用户等待时间。
- v2 的 18 次已记录局部渲染合计 **1044.80 秒**。
- v3 的 5 次已记录局部渲染合计 **220.30 秒**，共重编码 4,145 帧（多次修补可能重复计算同一帧）。
- 局部渲染计时包括该次补丁渲染与脚本验证；不包括寻找文字、生成模板、Agent 推理、视觉复核、拼接以及全片解码。
- 全片首轮并行墙钟时间、最终端到端耗时：**未建立完整统一计时，记为 null**。不从文件修改时间反推。

## 「积分」指 Codex 额度，不能用云 API 调用数替代

本地打码脚本使用 Apple Vision、OpenCV 与 FFmpeg，不需要逐帧调用云端视觉模型。**Codex Agent 的规划、代码修改、截图判断和复核仍然消耗账号额度。** 因此我们不能宣传「零额度」或「已经省了多少 Codex 积分」。

当前能核实的是父线程 session 的 `token_count` 遥测快照。它反复计入每轮对话上下文，其中大量输入命中缓存；这是 token 记录，不是账号额度比例、余额变化、现金账单或可兑换积分。缓存输入已包含在输入 token 中，reasoning 输出已包含在输出 token 中，不能再相加。

| 阶段 | 输入 token | 其中缓存输入 | 输出 token | 累计或差值 total |
| --- | ---: | ---: | ---: | ---: |
| 包装开始前，包含研发及视频迭代 | 81,129,923 | 79,516,800 | 276,127 | 81,406,050 |
| 本次包装，可见父线程差值快照 | 985,100 | 889,216 | 4,747 | 989,847 |

包装分界：用户正式包装请求在原 session 第 **6837 行**（2026-10-07 09:55:24 UTC），此前最新累计记录在第 **6831 行**；包装差值取第 **6942 行**（2026-10-07T09:59:36.472Z）的累计数减去该基线。这个快照采于包装进行中，后续工作及日志刷新会继续增加数值。

已检查的累计记录没有下降或 reset，但出现 **163 个重复累计事件**。若把每一条 `last_token_usage` 相加，会重复计数。本报告取累计快照及差值；不会将同一个累计数重复相加。

此处**没有汇总子 Agent 的 session token**，不能当作本项目全部 Agent 用量。已读取的原始来源仅为本线程确定的父 session：`rollout-2026-10-06T23-12-02-01a111c5-8f42-7e01-96ae-d06be53efdba.jsonl`；完整审计包不需要公开上传原始聊天日志。公开包保留抽取值、行号、时间和口径；对应两个原始 token_count 事件的有限摘录见 [codex-token-excerpts.json](../evidence/codex-token-excerpts.json)，不包含其它聊天内容。

账号当前额度另见 [codex-quota-snapshot.json](../evidence/codex-quota-snapshot.json)。它是全账号当前快照，可能包含其他任务的使用量；没有项目开始前的同口径快照，也没有官方 token→额度换算，因此不能推算本项目消耗了几点额度。

| 用户关心的成本指标 | 结论 |
| --- | --- |
| 本项目实际消耗多少 Codex 额度/积分 | 未知，null |
| 节省多少 Codex 额度/积分 | 缺同条件基线，null |
| 子 Agent 总 token | 本次未汇总，null |
| 现金成本 | 缺账单与计费口径，null |
| 此本地扫描流程逐帧云视觉 API 请求 | 0 |

## 可复现的调用数量对照

如果另一个方案按原视频**每一帧发一次云端视觉 API 请求**，这个 63,871 帧案例需要 63,871 次请求。我们的首轮 `detect_every=1` 在本地扫描每帧，逐帧云视觉 API 请求为 0。这个假设下可替换 **63,871 次逐帧云请求（100%）**。

这是明确设定的反事实对照，不是已经跑过、测过费用的旧方案。额外局部 OCR、模板匹配、人工抽查和 Agent 图片判断没有计入这个帧数；不能由这个对照推导 Codex 额度节省、画面推理费用、完成质量或手工剪辑工时。

## 可以直接引用的说明

> 这次 4K 案例，5 分钟素材的首轮自动扫描与导出用时 13 分 56 秒。全片 35 分 29 秒、63,871 帧；本地打码流程无需逐帧云端视觉 API。Agent 复核与多轮修补另计。Codex 额度消耗与节省还没有可核实的项目计费数据。

> In this 4K case, the first automatic pass scanned and exported a 5-minute segment in 13 min 56 sec. The full video contains 63,871 frames over 35 min 29 sec. The local redaction pipeline requires no per-frame cloud vision API. Agent review and iterative fixes are separate. Project-specific Codex allowance consumption and savings have not been established.

## 审计范围

读取了本工作区初稿/全片/v2/v3 的报告、分段完成标记、局部渲染日志、完整技术验证与 73 个原生像素对照记录；读取了已有 video-link-redactor Skill 与相关处理脚本；只读取明确属于本线程的父 session JSONL。具体输入文件的路径、字节大小和 SHA-256 在 metrics.json 的 `input_files`。源视频本体在本次指标审计中未解码，视频参数引用已经完成的技术验证；原视频及完整工作区由本地复查交接包另行带上。未读取凭证、无关会话或子 Agent 会话。
