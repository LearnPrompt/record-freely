# coding: utf-8
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json
ROOT=Path('/Users/carl/Documents/Codex/2026-10-06/1-openai-gpt-6-1-ultra'); BASE=ROOT/'work/real-video-audit'; OUT=ROOT/'outputs/带封面-前5分钟'
FONT=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',32)
SMALL=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',26)
def sheet(name,title,items,foot):
 width=1640;pad=20;prepared=[]
 for n,roi,label in items:
  im=Image.open(BASE/f'qa-final-actual-{n:04d}.jpg').convert('RGB')
  if roi:im=im.crop(roi)
  im.thumbnail((1600,1100),Image.Resampling.LANCZOS)
  prepared.append((im,label))
 height=96+sum(im.height+58 for im,label in prepared)+86
 canvas=Image.new('RGB',(width,height),'#f3f4f6');d=ImageDraw.Draw(canvas);d.text((pad,22),title,font=FONT,fill='#17202a');y=88
 for im,label in prepared:
  d.text((pad,y),label,font=SMALL,fill='#17202a');y+=44
  canvas.paste(im,(pad,y));y+=im.height+14
 d.text((pad,y+10),foot,font=SMALL,fill='#4b5563')
 canvas.save(OUT/name,quality=93)
sheet('检查样张-01-移动缩放.jpg','真实成片：移动 / 缩放与橙色字幕',[
 (2172,(200,350,2200,850),'01:12.400 · 两条网址分别遮住，正文行保留'),
 (2182,(600,1220,2200,1550),'01:12.733 · 网址缩小后灰条相应缩短，橙字幕保留'),
 (2211,(600,1220,2200,1550),'01:13.700 · 灰条跟随文字，橙字幕前景与下方中文保留')],
 '全部画面取自最终 redacted.mp4；此图展示局部抽查，非全片零漏码证明。')
sheet('检查样张-02-正文与侧栏.jpg','真实成片：正文、标题、侧栏中的重复域名',[
 (4560,None,'02:32.000 · 侧栏、标题、来源地址、方法句分别遮罩'),
 (4260,(2700,760,3450,960),'02:22.000 · 中文邻接域名按单词收紧')],
 '灰条随域名字号改变大小；正文邻字可能有极少边缘被遮。')
sheet('检查样张-03-长网址与转场.jpg','真实成片：长网址、字幕重合与转场',[
 (4800,(400,1300,3300,1850),'02:40.000 · 完整遮网址；灰条穿过部分白色大字幕笔画'),
 (4847,(400,1300,3300,1850),'02:41.567 · 长路径尾部一并覆盖'),
 (4848,(400,1300,3300,1850),'02:41.600 · 转场缩放时补住尾部；模糊前端未确认可读')],
 '此处白色半透明字幕没有前景还原，观看时会看到细灰条穿过字幕。')
sheet('检查样张-04-误判撤销.jpg','真实成片：撤掉章节、代码、图示的误判',[
 (2774,(600,1350,3000,1750),'01:32.467 · 代码属性保留；同画面真网址仍打码'),
 (6782,(1800,0,3250,140),'03:46.067 · 顶部章节标题恢复'),
 (7031,(1800,0,3250,140),'03:54.367 · 另一处章节标题恢复'),
 (7611,(2350,350,3200,650),'04:13.700 · 手机图示小标题保留')],
 '仅撤销已确认的误判候选及其相关跟踪、回填框。')
text=(BASE/'qa-visual-report-draft.md').read_text()
text=text.replace('修复阶段用最终遮罩记录在原片上合成，复核 29 个已知问题及邻接帧。最终交付视频还须重新解码取样核验，最终样张仅从真正输出视频生成。不是全片逐帧人工观看，抽样未见漏字不等于全片零漏码；未抽中的瞬时运动、极小字或 OCR 未认出的网址仍有漏识别可能。','修复阶段用最终遮罩记录在原片上合成，复核 29 个已知问题及邻接帧；终稿导出后，再从真正的 redacted.mp4 精确解码 63 个样帧，重点目检已知漏码、误判、缩放运动和切镜邻帧。已确认的缺陷在这些抽查点已修复，未确认新的可读网址泄漏。以下样张全部来自该真实终稿。\n\n这不是全片逐帧人工观看：前述粗采样、首轮 56 对照及最终 63 解码样本互有重叠；没有将全部 9000 帧逐帧人工精看。未抽中的瞬时运动、极小字或 OCR 未认出的网址仍有漏识别可能，抽查结果不能证明全片零漏码。')
text=text.replace('修复与预期效果','最终样帧核验结果')
text=text.replace('按蓝色链接文字行补遮，尽量不扩大到正文','按蓝色链接文字行补遮；完整覆盖网址，但细灰条穿过白色大字幕的部分笔画')
text=text.replace('橙色大字幕与网址重叠的地方保留橙字幕前景，灰条只挡后面的网址。','橙色大字幕与网址重叠的地方保留橙字幕前景及约 2 像素边缘。02:40 附近白色半透明“Agent能记住”字幕没有使用此还原规则：灰条穿过部分字幕笔画，完整网址覆盖优先。样张 03 明确展示这一观看取舍，不能宣称全部字幕像素完整保留。')
text=text[:text.index('## 最终输出复核（待完成）')]+'''## 最终输出复核与样张

实际成片共解码取出 63 个样帧，检查遮罩确实写入视频。网址出现/消失邻帧、Git 两行缩放、橙字幕重合、正文与侧栏域名、长路径尾部及已撤误判框均在抽查范围内。此项是视觉抽样复核；全片解码、9000 帧数量、拼接边界与音轨验证由主流程另行记录。

- [样张 01：移动缩放与橙字幕](检查样张-01-移动缩放.jpg)
- [样张 02：正文与侧栏](检查样张-02-正文与侧栏.jpg)
- [样张 03：长网址与转场，包括白字幕笔画被灰条穿过的效果](检查样张-03-长网址与转场.jpg)
- [样张 04：误判撤销](检查样张-04-误判撤销.jpg)

实际成片解码样本的帧号（从 0 开始，时间为帧号 ÷ 30）：

'''
checks=json.loads((BASE/'qa-final-output-check.json').read_text())
text+='`'+', '.join(str(s['frame']) for s in checks['samples'])+'`\n'
(OUT/'视觉检查.md').write_text(text)
print('published visual report and 4 final-only sample sheets')
