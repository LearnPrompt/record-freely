import subprocess,numpy as np
class Frames:
 def __init__(self,source,start_frame,frames):
  self.p=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-threads','4','-reinit_filter','0','-ss',f'{start_frame/30:.10f}','-i',str(source),'-t',f'{frames/30:.10f}','-map','0:v:0','-an','-vf','fps=30','-pix_fmt','bgr24','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=1024*1024)
 def read(self):
  n=3840*2160*3;raw=self.p.stdout.read(n)
  if len(raw)!=n:raise RuntimeError(('frame decode',len(raw),self.p.stderr.read().decode()))
  return np.frombuffer(raw,np.uint8).reshape(2160,3840,3)
 def close(self):
  self.p.stdout.close()
  try:self.p.wait(timeout=10)
  except subprocess.TimeoutExpired:self.p.terminate();self.p.wait()
