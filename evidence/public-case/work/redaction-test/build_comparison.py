#!/usr/bin/env python3
"""Build an audio-preserving before/after demo from final actual algorithm output."""
import argparse
import subprocess
from pathlib import Path
import cv2
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('redacted',type=Path)
parser.add_argument('--output',type=Path,default=ROOT.parent.parent/'outputs/link-redactor-demo-comparison.mp4')
args=parser.parse_args()
args.output.parent.mkdir(parents=True,exist_ok=True)
font=ImageFont.truetype('/System/Library/Fonts/STHeiti Light.ttc',21)
source=cv2.VideoCapture(str(ROOT/'source.mp4'));result=cv2.VideoCapture(str(args.redacted))
fps=source.get(cv2.CAP_PROP_FPS)
cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','960x318','-r',str(fps),'-i','pipe:0','-i',str(args.redacted),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','17','-pix_fmt','yuv420p','-c:a','copy','-shortest','-movflags','+faststart',str(args.output)]
f=subprocess.Popen(cmd,stdin=subprocess.PIPE)
frames=0
while True:
    ok0,a=source.read();ok1,b=result.read()
    if not ok0 or not ok1:
        if ok0!=ok1:raise RuntimeError('Source and result lengths differ')
        break
    canvas=Image.new('RGB',(960,318),(241,243,245))
    draw=ImageDraw.Draw(canvas)
    draw.text((20,12),'原始画面',font=font,fill=(45,50,60))
    draw.text((500,12),'自动打码 · 本地识别',font=font,fill=(45,50,60))
    for x,im in ((0,a),(480,b)):
        tile=Image.fromarray(cv2.cvtColor(im,cv2.COLOR_BGR2RGB)).resize((480,270))
        canvas.paste(tile,(x,48))
    draw.line((479,0,479,317),fill=(210,216,223),width=2)
    f.stdin.write(canvas.tobytes());frames+=1
f.stdin.close();assert f.wait()==0
source.release();result.release()
print(f'{args.output.resolve()} ({frames} frames)')
