import json,os,signal,subprocess,sys,time,threading
from pathlib import Path
from unittest.mock import patch
from supervisor.workers import process as m
root=Path('/tmp/m0r-fresh-review-2'); out={}
def request(s,**kw): return m.ProcessRequest((sys.executable,'-c',s),root,root,{},timeout_seconds=.1,**kw)
def summary(r):return {k:(len(v) if isinstance(v,bytes) else v) for k,v in r.__dict__.items()}
# Finite inherited child keeps both pipes open .65s, self-exits. Watchdog below.
s="import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(.65)'])"
t=time.monotonic();r=m.ProcessRunner().run(request(s));out['posix_inherited_drain']={'actual_wall':time.monotonic()-t,'result':summary(r)}
with patch.object(m,'_is_posix',return_value=False):
 t=time.monotonic();r=m.ProcessRunner().run(request(s,require_tree_cleanup=False));out['threads_inherited_close']={'actual_wall':time.monotonic()-t,'result':summary(r)}
# Buffered read loses short flushed output during timeout.
with patch.object(m,'_is_posix',return_value=False):
 r=m.ProcessRunner().run(request("import os,time;os.write(1,b'short');os.write(2,b'err');time.sleep(.4)",require_tree_cleanup=False));out['threads_short_timeout']=summary(r)
# Verify returned tree confirmation despite surviving descendant that escaped group.
pidfile=Path('/tmp/m0r-review2-evidence/escaped.pid')
s=f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',\"import os,time;open({str(pidfile)!r},'w').write(str(os.getpid()));time.sleep(.8)\"],start_new_session=True);time.sleep(.7)"
r=m.ProcessRunner().run(request(s));pid=int(pidfile.read_text());alive=True
try:os.kill(pid,0)
except ProcessLookupError:alive=False
out['escaped_tree']={'result':summary(r),'descendant_alive':alive}
if alive:
 try:os.kill(pid,signal.SIGKILL)
 except ProcessLookupError:pass
# Track queue highwater with deliberately delayed consumer; finite writer, actual queues unbounded.
import queue
orig=queue.Queue;queues=[]
class Q(orig):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.high=0;queues.append(self)
 def put(self,item,*a,**kw):super().put(item,*a,**kw);self.high=max(self.high,self.qsize())
 def get_nowait(self):
  if self.high==0:time.sleep(.03)
  return super().get_nowait()
with patch.object(m,'_is_posix',return_value=False),patch.object(queue,'Queue',Q):
 r=m.ProcessRunner().run(request("import os;os.write(1,b'x'*4000000)",require_tree_cleanup=False,max_output_bytes=64));out['thread_queue_bound']={'result':summary(r),'queue_maxsizes':[q.maxsize for q in queues],'highwater_chunks':[q.high for q in queues]}
Path('/tmp/m0r-review2-evidence/new-results.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
