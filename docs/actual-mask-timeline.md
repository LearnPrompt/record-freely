# 按实际打码跳转

全片背景融合或持续导航遮罩不适合作为跳转点。查看器应按局部隐私遮挡真正出现的连续区间组织，另保留长区间内的缩放、闪烁、尾字符等检查点。用背景色填充的局部隐私遮罩仍属于打码；颜色不能决定是否排除。

`scripts/build_review_timeline.py` 导出已审阅记录的 JSON、CSV 和 Markdown 时间轴，不检测视频，也不直接生成播放器。Agent 可将 `start_seconds` 用于查看器的跳转按钮；不要按分钟或每五秒默认分段。原片已有且未登记的遮罩不会自动进入索引。

## 输入格式

在私有任务目录编写下列匿名清单。数字是成片 CFR 时间轴的帧号，区间为零起点、左闭右开；`source_cuts` 则在原片帧坐标中。SHA 必须是最终编码文件的真实 SHA256：

```json
{
  "fps": "30/1",
  "output_frames": 120,
  "source_frames": 126,
  "encoded_sha256": "replace-with-real-64-character-lowercase-sha256",
  "source_cuts": [[60, 66]],
  "events": [
    {"role": "local_redaction", "start_frame": 10, "end_frame": 20},
    {"role": "global_protection", "start_frame": 0, "end_frame": 120},
    {"role": "ai_label", "start_frame": 30, "end_frame": 60}
  ]
}
```

每项必须经审阅标明角色：`local_redaction`、`global_protection`、`ai_label`、`trusted_restoration` 或 `keep`。仅第一类生成打码跳转。自动灰块报告通常把非空 `boxes` 对应的帧标为局部打码；含有序图层的复杂报告必须逐类确认，不能把所有实色矩形当链接，也不能按自定义 ID 子串泛化分类。

```bash
python3 scripts/build_review_timeline.py /absolute/reviewed-events.json \
  --video /absolute/final.mp4 --output-dir /absolute/new-timeline
```

`--video` 流式核对成片哈希，无需额外加载模型；省略时输出明确记录 `video_sha_verified: false`。已有目录不会覆盖。清单里的 FPS/帧数仍需技术验收，哈希匹配不能替代这些检查。脚本只导出必要数字和角色计数，不透传原始 OCR 文本、ID、文件路径或任意注释。

## 连续区间与查看器验收

仅合并相接或重叠的局部打码，不能跨过一个未打码帧，也不能越过原片删减产生的时间跳变。源片剪掉的时间不能直接作为成片 seek；使用导出的两套坐标。空清单意味着没有登记局部打码，不是证明视频没有敏感内容。

查看器需有上一处／下一处、类别筛选以及长区间内的重点时间按钮。记录应绑定成片 SHA256，旧标注不能串到新版本。播放失败时先检查 UI；修复展示不需要重编码成片。`currentTime`、`readyState`、元数据或完整 FFmpeg 解码成功不能证明屏幕显示了该帧，必须在实际浏览器中看到跳转后的非黑画面并检查内容；如采用 canvas 回退，继续验收实际可见帧与音画同步。
