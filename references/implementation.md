# 实现、补丁与复现

## 两层入口

- `redact_video.py`：原可运行的本地引擎副本。FFmpeg 在临时目录生成 FFV1 恒定帧率中间片；macOS Vision persistent Swift worker 每帧识别并给出字符边界；Python 识别 HTTP(S)、www 与 IANA 顶级域名。普通文件扩展名、电子邮件、代码调用不默认当网址。字符框缺失时退回整行，可能多挡，需要审阅。真实一分钟试用还发现 Vision 有时为每个字符返回同一个整行框；这类框保守保留，报告标记 `repeated_character_boxes`，不能当成精确字符定位。该标签修正不自动解决多挡，需要源帧审阅。
- OpenCV 在短暂 OCR 空缺期间验证当前帧模板，逐步测试 0.94/1.00/1.06 倍尺度；匹配低于阈值、画面切换或最大追踪期结束则停止。向前回补也要求每帧视觉证据。96 MiB 回看缓存不包括 FFV1 中间片：长 4K 原片需要充足临时磁盘，不能宣称整个运行只用 96 MiB。
- `stabilize_masks.py`：从实际 v3 稳框逻辑抽取。显式场景边界、缺帧/不连续索引都会断开；只输出原报告中的帧。稳定静止段用固定包络；移动框保持当前检测框的覆盖；缩放变化分段。算法可能扩大邻近内容遮挡，仍需要人工审阅。
- `refine_video.py`：读取密集 0 开始的片段报告，从原片流式重新渲染。自动引擎按 1 MiB 块对原文件计算完整 `source_sha256`；refine 在探测解码及创建输出前重新核对，防止同尺寸、同修改时间的无关影片误用矩形。内容相同的副本即使路径/mtime 改变也接受，开始时重记当前 stat；旧报告没有此字段时必须重跑自动引擎。运行中仍核对原文件尺寸/修改时间，报告不保存媒体内容。不重新 OCR，不采纳影片特定的路径、章节、颜色恢复或 GOP 脚本。全帧重编码与案例 v3 的精细 GOP 局部重渲染不同，不能套用 v3 的速度或原 AAC 保持指标。

这些入口都是本地代码，不主动调用云 API，不上传画面。Agent 读取源码、运行工具与复查仍消耗 Codex 额度；本地 OCR 没有模型 API 账单，不等于 Codex 消耗为零。只有前后同口径账单/额度快照才能计算“节省多少”；测试的 `elapsed_seconds` 是本次进程墙钟时间，并非全部人工复查时间。

## 运行条件

macOS、Xcode Command Line Tools（`xcrun swiftc`）、FFmpeg/FFprobe、Python 3.9+、`opencv-python`、`numpy`。测试另需 `pytest` 与 `Pillow`。先检查已有环境，缺依赖时使用任务虚拟环境，勿更改全局环境。

```bash
python3 -c 'import cv2, numpy; print(cv2.__version__)'
ffmpeg -version
xcrun --find swiftc
```

SDR 支持 1–120 fps，输出 CFR H.264/yuv420p；奇数尺寸右/下补到偶数。AAC 输出保持音轨数量和所选窗口的延迟，音频重新编码。VFR/旋转/HDR 或复杂音轨需额外审阅。自动报告完成时检查帧数、时长和音轨数量；refine 另做 `ffmpeg -xerror` 完整解码，仍不等同于完整的视觉漏码审查。

## 匿名人工补丁 v1

补丁 SHA256 必须绑定**传给 refine 的那份原始 report.json 字节**。帧号是 `report.json` 内的本次处理片段编号，从 0 开始；即使原片预览从 60 秒开始也用片段帧号。坐标是归一化源片尺寸的像素 `[x, y, width, height]`，整数、在画面内。

```bash
python3 -c 'import hashlib; from pathlib import Path; print(hashlib.sha256(Path("/absolute/full/report.json").read_bytes()).hexdigest())'
```

```json
{
  "version": 1,
  "source_report_sha256": "REPLACE_WITH_EXACT_REPORT_SHA256",
  "frames": {
    "42": {"boxes": [[120, 80, 180, 28], [340, 160, 90, 24]]},
    "43": {"boxes": []}
  }
}
```

稳框输出会使用新的 `S*` 区域 ID，原自动检测的 `U*` ID 保存在 `source_ids` 中。根据自动 ID 筛选稳框区域时应检查 `source_ids`，否则取消误遮的脚本可能没有作用；仍须看实际像素。

每个指定帧的 `boxes` **完整替换**该帧全部遮挡；没有列出的帧保留原框。空数组明确取消该帧遮挡。不是“在原框上添加一个框”，因此修一行时必须携带该帧其他应保留的框。先稳框，后人工替换，避免窄的作者/后缀保护框再被包络扩大。补丁不能跨报告静默复用；不支持任意执行、字幕颜色恢复或从未审阅媒体自动生成身份路径掩码。

## 可复现测试

从 Skill 根目录执行。单测在 pytest 临时目录生成小视频，不改输入。真实 OCR 夹具在独立的新目录生成 6 秒/144 帧视频，包含横移、三帧短闪、滚动、无链接硬切和普通文字。

```bash
python3 -m pytest -q tests
python3 tests/generate_fixture.py --output-dir /absolute/new-fixture
python3 scripts/redact_video.py /absolute/new-fixture/source.mp4 \
  --output-dir /absolute/new-fixture/automatic --ocr-workers 3
python3 tests/verify_fixture.py /absolute/new-fixture/automatic/redacted.mp4 \
  --fixture-dir /absolute/new-fixture \
  --report /absolute/new-fixture/automatic-acceptance.json \
  --contact /absolute/new-fixture/automatic-contact.png
python3 scripts/refine_video.py /absolute/new-fixture/source.mp4 \
  --report /absolute/new-fixture/automatic/report.json \
  --stabilize --output-dir /absolute/new-fixture/stable
python3 tests/verify_fixture.py /absolute/new-fixture/stable/redacted.mp4 \
  --fixture-dir /absolute/new-fixture \
  --report /absolute/new-fixture/stable-acceptance.json \
  --contact /absolute/new-fixture/stable-contact.png
```

验收用解码像素比较合成链接的字墨是否被遮、普通文字变化及切镜后是否遗留遮挡。它验证此夹具的可观察效果，不证明任何现实录屏全部链接可被识别。人工后缀/路径、白色章节字与鼠标高亮冲突等 v3 精细处理保留在案例本地源包，不能声称这些都已泛化自动完成。

## 来源与维护

引擎、Swift worker、TLD 快照及原回归单测来自本项目实测的 `video-link-redactor`；稳框核心来自本片 v3 的 `stabilize_masks.py`，现在明确支持报告场景边界与不连续索引，不硬编码 30 fps 或分块起点。IANA TLD 文件是附带离线快照，不运行更新请求。提交时把快照、Swift 源码与测试一同保留；可以从源码重新编译，不能仅交付某台机器的二进制。
