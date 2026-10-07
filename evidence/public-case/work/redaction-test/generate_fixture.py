#!/usr/bin/env python3
"""Local synthetic link redaction fixture; no network and no secrets."""
import json
import math
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
W, H, FPS, N = 960, 540, 24, 144
font_path = '/System/Library/Fonts/Supplemental/Arial.ttf'
normal_font = ImageFont.truetype(font_path, 25)
link_font = ImageFont.truetype(font_path, 27)
small_font = ImageFont.truetype(font_path, 24)
label_font = ImageFont.truetype(font_path, 17)
frames = []
command = ['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=6','-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','15','-pix_fmt','yuv420p','-c:a','aac','-b:a','96k','-t','6','-movflags','+faststart',str(ROOT/'source.mp4')]
proc = subprocess.Popen(command, stdin=subprocess.PIPE)

def draw_text(draw, xy, text, font, fill):
    box = draw.textbbox(xy,text,font=font)
    draw.text(xy,text,font=font,fill=fill)
    x0,y0,x1,y1=box
    return [x0-2,y0-2,x1-x0+4,y1-y0+4]

for i in range(N):
    img=Image.new('RGB',(W,H),(244,246,249))
    draw=ImageDraw.Draw(img)
    draw.rounded_rectangle((24,25,936,515),radius=18,fill=(255,255,255),outline=(208,215,222),width=2)
    normal=[]
    normal.append(draw_text(draw,(52,53),'Normal tutorial text must remain readable.',normal_font,(42,45,50)))
    normal.append(draw_text(draw,(52,95),'Camera moves; content should stay comfortable to watch.',small_font,(66,70,75)))
    boxes=[]
    texts=[]
    if i<48:
        x=52+4*i
        boxes.append(draw_text(draw,(x,185),'https://example.com/private',link_font,(36,92,171)))
        texts.append('https://example.com/private')
        draw_text(draw,(52,145),'SCENE A  |  Horizontal motion',label_font,(105,110,120))
    elif i<60:
        draw_text(draw,(52,145),'SCENE B  |  A URL appears for only three frames',label_font,(105,110,120))
        if 50<=i<=52:
            boxes.append(draw_text(draw,(330,237),'go.example.org',link_font,(36,92,171)))
            texts.append('go.example.org')
    elif i<112:
        draw_text(draw,(52,145),'SCENE C  |  Vertical scrolling',label_font,(105,110,120))
        y=400-4*(i-60)
        boxes.append(draw_text(draw,(300,y),'docs.example.org/guide',link_font,(36,92,171)))
        texts.append('docs.example.org/guide')
    else:
        draw.rectangle((30,133,930,505),fill=(235,241,230))
        normal.append(draw_text(draw,(70,235),'A hard cut. No links on this screen.',normal_font,(40,55,40)))
        normal.append(draw_text(draw,(70,285),'Only ordinary words and numbers: 2026, 42.',small_font,(60,75,60)))
    frames.append({'frame':i,'time':i/FPS,'links':boxes,'link_texts':texts,'normal':normal})
    if i in (0,50,80,120):
        img.save(ROOT/f'frame-{i:03d}.png')
    proc.stdin.write(img.tobytes())
proc.stdin.close()
if proc.wait()!=0:
    raise SystemExit('ffmpeg failed')
truth={'width':W,'height':H,'fps':FPS,'frames':frames,'short_url_frames':[50,51,52],'hard_cut_start':112,'description':'All links are synthetic example domains. Boxes are [x,y,width,height].'}
(ROOT/'truth.json').write_text(json.dumps(truth,ensure_ascii=False,indent=2))
print(ROOT/'source.mp4')
print(ROOT/'truth.json')
