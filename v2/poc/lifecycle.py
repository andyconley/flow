"""Observe only descendants of a POC-owned root; identity-check before cancellation."""
import os,signal,subprocess,time

def snapshot():
 result={}
 text=subprocess.check_output(['ps','-axo','pid=,ppid=,lstart='],text=True)
 for line in text.splitlines():
  parts=line.split()
  if len(parts)>=7:result[int(parts[0])]={'parent':int(parts[1]),'birth':' '.join(parts[2:7])}
 return result

class ProcessScope:
 def __init__(self,pid):self.root=pid;self.known={};self.observe()
 def observe(self):
  current=snapshot();changed=True
  while changed:
   changed=False
   for pid,info in current.items():
    if pid not in self.known and (pid==self.root or info['parent'] in self.known):
     self.known[pid]=info;changed=True
  return {pid:info for pid,info in current.items() if pid in self.known and info['birth']==self.known[pid]['birth']}
 def stop(self):
  errors=[]
  for sig in [signal.SIGTERM,signal.SIGKILL]:
   alive=self.observe()
   for pid in sorted(alive,reverse=True):
    try:os.kill(pid,sig)
    except ProcessLookupError:pass
    except PermissionError:errors.append(pid)
   time.sleep(.2)
  return {'alive':list(self.observe()),'signal_errors':errors}
