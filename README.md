# 放心录 · Record Freely

**先把内容录下来，再把需要遮挡的地方交给 Agent。**

[English](README_EN.md) · [日本語](README_JA.md) · [GitHub](https://github.com/LearnPrompt/record-freely) · [下载与一分钟样片](https://github.com/LearnPrompt/record-freely/releases/tag/v1.0.0) · [公开复查](docs/public-review.md)

[前后对比](assets/comparisons/index.html) · [实现说明](references/implementation.md) · [成本与耗时](docs/cost-and-time.md) · [在线拖动滑杆](https://learnprompt.github.io/record-freely/)

录教程时，总有一些瞬间让人停下来：终端里突然出现链接，文件路径带着自己的用户名，页面一放大，原本不起眼的地址占了半个屏幕。怕发布时被误判，于是重录、剪掉、逐帧补码。最后，被打断的是你想分享的那件事。

放心录来自一次真实的修改。我们在影视飓风相关剪辑工作流的录屏里，处理了一段 **35 分 29 秒、4K、30fps** 的视频。最开始能盖住地址，但框会抖，会把 Skill 名字盖掉，也会在鼠标高亮时漏掉一行。跟着实际反馈，我们把作者与 Skill 名字留下，把 `/Users/…/` 身份前缀遮掉，再让停住的框保持稳定、移动的框跟着画面走。

这就是 LearnPrompt 一直在做的事：从“看见可以做到”，到“学会怎么做”，再到“做成一个自己能复用的工具”。这一次，不用因为屏幕里一个地址而中断分享。

## 看看改了什么

同一源帧、同一裁切范围，前后都保留真实文字。对照图中 BEFORE 展示原本可见的地址；它用于解释遮挡范围。

### 留下 Skill 的找法

只遮链接前半段，留下作者和 Skill 名字。这项选择由人工确认源字形，再写入修改区域；不是默认自动猜作者。

![01:02 同帧对照：保留作者和 Skill 名称](assets/comparisons/01-02-comparison.jpg)

![06:39 同帧对照：缩放后仍保留 Skill 的作者与名称](assets/comparisons/06-39-comparison.jpg)

### 文件路径保留用途，身份前缀收起来

`Downloads/…/clips` 和文件名帮助观众理解工作流。遮掉身份前缀，观众仍然能跟着操作。连续帧检查覆盖了鼠标高亮、滚动、边缘裁切和章节标题交叠。

![09:00 同帧对照：遮身份前缀，保留目录和文件名](assets/comparisons/09-00-comparison.jpg)

[拖动滑杆查看真实前后对比](assets/comparisons/index.html)。这是围绕影视飓风内容展开的独立创作者技术示例；名称用于交代案例背景，不表示官方合作。

## 怎么用

目前支持 **macOS**。需要 Xcode Command Line Tools、FFmpeg、Python 3，以及 `opencv-python` 和 `numpy`。处理过程在本机完成，视频帧不会被引擎上传到云端。**无需额外下载 YOLO 或 OCR 模型权重**：文字识别使用 macOS 自带 Apple Vision；Swift 源码由 Xcode 命令行工具编译。

从仓库取得完整源码，再复制到 Agent 的 skills 目录。例如 Codex：

```bash
git clone https://github.com/LearnPrompt/record-freely.git
mkdir -p ~/.codex/skills
cp -R record-freely ~/.codex/skills/
```

也可通过支持的 Skill 安装器尝试 `npx skills add LearnPrompt/record-freely`；此安装器命令尚未在本次交付中验证。已有同名 Skill 时先保留旧副本。

然后告诉 Agent：

> 用 $record-freely 处理这条录屏。只遮看起来像链接的内容；保留教学文字。先做短预览，检查缩放、滚动和闪烁，再输出完整视频与检查报告。

也可以直接运行自动初稿：

```bash
python3 scripts/redact_video.py /absolute/input.mp4 \
  --output-dir /absolute/new-output --ocr-workers 3
```

OCR 先找文字，再用离线域名规则筛选疑似链接；OpenCV 模板匹配跟随位置与缩放。稳框阶段对静止文字使用固定覆盖框，遇到移动、缩放、切镜或检测间隙分段处理，减少框大小反复变化。

人工修改和稳框入口见 [实现说明](references/implementation.md)。自动检测、人工修补和最终检查是不同阶段，报告会分别说明。输入源片保持不变，输出使用新目录。

## 这次实测

| 项目 | 可核实结果 |
| --- | --- |
| 素材 | 35:29.033，3840 × 2160，30fps，63,871 帧 |
| 一个 5 分钟片段的自动初稿 | 13 分 56 秒；这是首段实测，不含开发、人工修订和最终验收 |
| 本地方案 | Apple Vision OCR + OpenCV 跟踪/稳框 + FFmpeg；不调用云端视觉模型 |
| 最终技术检查 | 全片视频/音频完整解码、连续 PTS、原音轨编码包一致、采样同步通过 |
| 最终合并对照 | 73 个准确时间戳取样点与已复验分段的原生像素一致 |
| Codex 额度 | Agent 会消耗 Codex 额度；会话 token 记录不能直接换算额度，项目额度和节省量尚无账单归因 |

[成本与耗时](docs/cost-and-time.md)附记录来源。不能把“本地处理无云端 API 调用”说成“Codex 零消耗”，也不能把一个片段的自动初稿时间说成全片终稿时间。未来对同一片段、同一验收标准做基线测试，才有依据谈额度节省。

## 它能帮到哪里

放心录检测**视觉上像网址的文字**，跟随其移动和缩放，并用较小的实色框遮挡。路径、指定词、链接保留哪几段，可通过审阅后的区域修改实现。默认不把所有路径、邮箱和 `.html` 文件名都当网址。

这能减少发布前可见地址带来的顾虑，但平台规则与识别结果不由 Skill 控制；它不能保证过审。最终仍要看链接首尾、缩放、切镜与邻近文字。本案例还有一个旧反馈未定位：25:41 的 `.html`，准确源帧为天平动画，保留在复查记录中。

69 项代码测试和 144 帧真实 OCR 合成夹具通过。独立 Agent 从源码复跑、逐像素核对六张真实对照图，并重新计算完整复查数据集哈希；发现的源视频绑定问题已修复并复验。见[独立复查](docs/independent-review.md)。

## 交给下一个 Agent

从 [公开复查入口](docs/public-review.md)开始：网页可读源码、测试、三语说明、同帧对照与匿名指标证据，不必下载整部原片。需要实跑时，在 [v1.0.0 Release](https://github.com/LearnPrompt/record-freely/releases/tag/v1.0.0)取得 `trial-source-00m55s-01m55s.mp4`：原片 **00:55–01:55**，1 分钟、4K、30fps。新 Agent 的实跑结果需另看实际报告，不能从历史案例推断。

完整历史数据集保存在本机 **full-review-bundle/**：原片、全部 work/ 与 outputs/、原实现和正式包快照，约 **68.5 GB**。公开的[全文件清单](evidence/full-review-file-catalog.json)记录路径、大小和 SHA-256；清单不是全部媒体的下载包。轻量公开复查与全量本地审计的范围见[复查说明](docs/reviewer-handoff.md)。

公开仓库与 Release 是交付目标，文件是否实际可读、可下载应以对应网页和发布验证记录为准。

由 [LearnPrompt](https://learnprompt.pro) 出品。把录屏里的一个麻烦，变成下一次可以直接调用的 Skill。
