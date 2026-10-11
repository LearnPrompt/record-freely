# 数字静音、指定语言与私有首遍诊断

这些命令只使用已有本地 FFmpeg、`whisper-cli` 和模型。示例路径是占位符，须换为用户授权的绝对路径；创建新的私有输出目录。不得将音频、原始转写、私有帧或工具 stderr 放进公开仓库。无模型时不自动下载。完整 PCM 信号检查只能证明数字静音，不能判断低音量是否能听清，也不能证明内容或版权已通过。

## 1. 完整解码信号证据

先用 FFprobe 确认音轨索引；逐条实际音轨检查，不能只检查第一轨就称全音频通过。下例完整解码音轨索引 `1` 为双精度浮点 PCM，统计所有样本峰值与解码 PCM SHA-256，不降为整数 PCM，以免小信号被量化成零。不做 `apad` 补静音；解码失败或没有样本不能判静音。

```bash
python3 - /absolute/final.mp4 1 <<'PY'
import hashlib, json, subprocess, sys
import numpy as np
source, track = sys.argv[1], int(sys.argv[2])
command = ['ffmpeg', '-v', 'error', '-nostdin', '-i', source,
           '-map', f'0:{track}', '-vn', '-f', 'f64le', '-acodec', 'pcm_f64le', '-']
process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
digest, peak, samples, remainder = hashlib.sha256(), 0.0, 0, b''
try:
    while True:
        chunk = process.stdout.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        raw = remainder + chunk
        complete = len(raw) // 8 * 8
        values = np.frombuffer(raw[:complete], dtype='<f8')
        if len(values):
            if not np.isfinite(values).all():
                raise RuntimeError('nonfinite_pcm')
            peak = max(peak, float(np.abs(values).max()))
            samples += len(values)
        remainder = raw[complete:]
    if process.wait() != 0 or remainder or not samples:
        raise RuntimeError('incomplete_pcm_decode')
    print(json.dumps({'audio_stream_index': track, 'samples': samples,
                      'peak': peak, 'digital_silence': peak == 0.0,
                      'decoded_pcm_sha256': digest.hexdigest()}))
finally:
    if process.poll() is None:
        process.kill()
        process.wait()
    process.stdout.close()
PY
```

保存输出在私有验证记录，另记媒体 SHA、实际音轨格式与解码范围。这是完整原音轨证据，不是每声道分别分析；所有样本都为零才确认数字静音。脚本语音检查另外针对实际选定窗口解码，并在请求 ASR 时跳过已确认的数字静音；没有请求 ASR、没有音轨与失败分别记录。不能把数字静音叫“ASR 检查没有命中”。

## 2. 指定语言补检查，保留源时间

先正常检查最终编码视频并绑定该版本报告；若人工听到英文但首遍遗漏，再明确指定英文和源视频上的窗口：

```bash
python3 scripts/review_video.py /absolute/final.mp4 \
  --output-dir /absolute/review-auto --privacy \
  --redaction-report /absolute/final/report.json \
  --asr-model /absolute/local-model.bin --asr-language auto

python3 scripts/review_video.py /absolute/final.mp4 \
  --output-dir /absolute/review-en --privacy \
  --redaction-report /absolute/final/report.json \
  --start 60 --duration 15 \
  --asr-model /absolute/local-model.bin --asr-language en
```

这里复扫坐标属于传入的 `final.mp4`；如果它是原片裁出的片段，另记原片到成片的偏移／剪切映射。内部 ASR 临时 SRT 是窗口相对时间，脚本候选会加回 `--start`。外部传给 `--subtitle` 的 SRT 必须已经使用输入视频零点坐标，不能把窗口零点当源片零点。不要合并原文时再次重复加偏移。

`auto` 只表示让本地模型选语言，不能证明全部语言都被识别。工具专名、指代、否定、对白仍需实际试听；指定语言失败与未检查单独报告。

## 3. 首遍诊断原文只在私有目录留证

`review_video.py` 为匿名报告检测后删除临时转写，不提供原文导出开关。需要诊断首遍幻觉或多语言遗漏时，另行在用户授权的私有目录先跑 Whisper；不要事后把一个重跑结果说成原首遍。下面是供诊断的最小独立例子，**仅适用于所选音轨起点与视频起点相同**的媒体；有延迟或负起点时先按实际音轨时间对齐，不能直接套这条抽取命令。

```bash
mkdir /absolute/new-private-audio-diagnostics
ffmpeg -v error -nostdin -i /absolute/final.mp4 \
  -map 0:a:0 -vn \
  -af 'asetpts=PTS-STARTPTS,atrim=start=60:end=75,asetpts=PTS-STARTPTS' \
  -ac 1 -ar 16000 /absolute/new-private-audio-diagnostics/window.wav
whisper-cli -m /absolute/local-model.bin \
  -f /absolute/new-private-audio-diagnostics/window.wav -l auto -osrt \
  -of /absolute/new-private-audio-diagnostics/first-auto \
  > /absolute/new-private-audio-diagnostics/first-auto.stdout.log \
  2> /absolute/new-private-audio-diagnostics/first-auto.stderr.log
whisper-cli -m /absolute/local-model.bin \
  -f /absolute/new-private-audio-diagnostics/window.wav -l en -osrt \
  -of /absolute/new-private-audio-diagnostics/supplement-en \
  > /absolute/new-private-audio-diagnostics/supplement-en.stdout.log \
  2> /absolute/new-private-audio-diagnostics/supplement-en.stderr.log
```

对 WAV 先用上面的完整 PCM 检查，确认非数字静音后才运行两条 Whisper 命令。保存源媒体 SHA、模型 SHA、工具版本、音轨索引、抽取区间 `[60,75)`、SRT 偏移 `+60`、语言、退出码和先后顺序；记录首次实际运行的结果，包括失败。首遍和补识别不得覆盖同一前缀。局部结果不冒充全轨覆盖。

原始 WAV、SRT 和日志可能含联系方式，只进入授权的私有证据包；匿名汇总仅保留类别、区间、语言与失败状态。清理脚本临时目录不等于删去已授权的诊断证据；私有文件的保留／删除按用户安排。诊断示例不会自动静音、修改字幕或判平台通过。
