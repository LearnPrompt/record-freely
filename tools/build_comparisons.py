# -*- coding: utf-8 -*-
"""Extract the same source/final frame for an auditable visual comparison."""
import argparse,json,subprocess
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
CASES=[('01-02',1860,[160,780,3220,1080],'Keep author / skill'),('06-39',11970,[110,1180,2720,1600],'Keep author / skill'),('09-00',16200,[180,565,2850,1680],'Hide identity / keep filenames')]
def frame(path,n):
 start=max(0,n//30-1)
 raw=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-threads','2','-ss',str(start),'-reinit_filter','0','-i',str(path),'-an','-vf',f'select=eq(n\\,{n-start*30})','-frames:v','1','-vsync','0','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
 if len(raw)!=3840*2160*3:raise ValueError('This case extractor expects the verified 3840x2160/30 case.')
 return Image.fromarray(np.frombuffer(raw,np.uint8).reshape(2160,3840,3))
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--final',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True);rows=[]
 font_path='/System/Library/Fonts/Supplemental/Arial.ttf';font=ImageFont.truetype(font_path,28)if Path(font_path).exists()else ImageFont.load_default()
 for label,n,crop,title in CASES:
  before,after=(frame(path,n).crop(crop)for path in [a.source,a.final]);width=1500;height=round(before.height*width/before.width)
  before=before.resize((width,height));after=after.resize((width,height));before.save(a.output_dir/f'{label}-before.png');after.save(a.output_dir/f'{label}-after.png')
  board=Image.new('RGB',(width,height*2+150),(14,23,32));draw=ImageDraw.Draw(board);draw.text((24,15),f'{label.replace("-",":")}  /  {title}',font=font,fill=(244,246,247));draw.text((24,55),'BEFORE',font=font,fill=(163,177,191));board.paste(before,(0,95));draw.text((24,height+110),'AFTER  /  Record Freely',font=font,fill=(127,225,178));board.paste(after,(0,height+150));board.save(a.output_dir/f'{label}-comparison.jpg',quality=95)
  rows.append({'id':label,'global_frame':n,'time_seconds':n/30,'crop_xyxy':crop,'source_size':[3840,2160],'comparison_method':'Same decoded CFR frame; identical crop and display scale; no text replacement.','before':f'{label}-before.png','after':f'{label}-after.png','board':f'{label}-comparison.jpg'})
 (a.output_dir/'manifest.json').write_text(json.dumps({'source':'带封面.mp4','final':'带封面-修正版v3/redacted.mp4','rows':rows,'authorization':'Creator requested before/after source-frame comparisons; unmasked BEFORE contains original visible text.'},ensure_ascii=False,indent=2))
 print('Same-frame comparisons generated',len(rows))
if __name__=='__main__':main()
