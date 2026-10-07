"""Bounded FFmpeg RGB pipe; same pixels as lossless normalization, no cache."""
from pathlib import Path
import subprocess
import cv2,numpy as np
class StreamCapture:
 def __init__(self,source,start,frames,width=3840,height=2160,fps=30,log=None):
  self.width,self.height,self.frames,self.fps=width,height,frames,fps;self.position=0;self.closed=False
  self.error=open(log,'w')if log else subprocess.DEVNULL
  cmd=['ffmpeg','-v','error','-nostdin','-threads','4','-ss',str(start),'-i',str(source),'-t',f'{frames/fps:.10f}','-map','0:v:0','-an','-vf',f'fps={fps:.10f}','-pix_fmt','bgr24','-f','rawvideo','pipe:1']
  self.process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=self.error,bufsize=1024*1024)
 def isOpened(self):return not self.closed
 def get(self,prop):
  return {cv2.CAP_PROP_FRAME_WIDTH:self.width,cv2.CAP_PROP_FRAME_HEIGHT:self.height,cv2.CAP_PROP_FRAME_COUNT:self.frames,cv2.CAP_PROP_FPS:self.fps,cv2.CAP_PROP_POS_FRAMES:self.position}.get(prop,0)
 def read(self):
  if self.closed or self.position>=self.frames:return False,None
  data=self.process.stdout.read(self.width*self.height*3)
  if not data:return False,None
  if len(data)!=self.width*self.height*3:raise RuntimeError('Partial RGB video frame from decoder')
  self.position+=1;return True,np.frombuffer(data,np.uint8).reshape(self.height,self.width,3)
 def release(self):
  if self.closed:return
  self.closed=True;self.process.stdout.close()
  try:self.process.wait(timeout=10)
  except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=10)
  if hasattr(self.error,'close'):self.error.close()
