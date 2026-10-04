import subprocess,sys,json,os,signal
from pathlib import Path
from unittest.mock import patch
from supervisor.workers import process as m
root=Path('/tmp/m0r-review-1');results={}
def req(script,**kw): return m.ProcessRequest((sys.executable,'-c',script),root,root,{},timeout_seconds=.2,**kw)
# Controlled single sleeping leader; denial cannot touch any unrelated group.
with patch.object(m.os,'killpg',side_effect=PermissionError('synthetic denied')):
 r=m.ProcessRunner().run(req('import time;time.sleep(2)'));results['killpg_denial']=r.__dict__
# Capture the process started by code, inject drive error, inspect and clean only it.
original=m.subprocess.Popen;captured=[]
def capture(*a,**k):
 p=original(*a,**k);captured.append(p);return p
with patch.object(m.subprocess,'Popen',side_effect=capture),patch.object(m.ProcessRunner,'_drive_process',side_effect=RuntimeError('synthetic drive failure')):
 r=m.ProcessRunner().run(req('import time;time.sleep(2)'));p=captured[0];results['drive_exception']={'result':r.__dict__,'leader_alive_after_return':p.poll() is None,'stdout_closed':p.stdout.closed,'stderr_closed':p.stderr.closed};p.kill();p.wait()
# Simulate unsupported Windows pipe select, preserve real POSIX process cleanup.
with patch.object(m,'_is_posix',return_value=False),patch.object(m.select,'select',side_effect=OSError('synthetic Windows non-socket pipe')):
 r=m.ProcessRunner().run(req("import os,time;os.write(1,b'x'*200000);time.sleep(2)",require_tree_cleanup=False));results['windows_pipe_select']=r.__dict__
# EOF on stderr makes it readable but provides no byte beyond stdout's exact budget.
r=m.ProcessRunner().run(req("import os,time;os.write(1,b'x'*64);os.close(2);time.sleep(.1)",max_output_bytes=64));results['exact_budget_live_eof']=r.__dict__
# Inherited pipe must not turn a .1s wall deadline into .6s drain wait; bounded child exits itself.
r=m.ProcessRunner().run(m.ProcessRequest((sys.executable,'-c',"import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(.6)']);"),root,root,{},timeout_seconds=.1));results['inherited_pipe_drain']=r.__dict__
for r in results.values():
 d=r.get('result',r)
 for key in ['stdout','stderr']:
  if key in d:d[key]=d[key].decode('utf-8',errors='replace')
Path('/tmp/m0r-review-evidence/probes.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
from supervisor.agents.base import parse_agent_result
identity=dict(task_id='M0R-review2-remediation',run_id='m0r-run-1',attempt_id='m0r-attempt-1',role='implementer',provider='mock')
protocol=dict(schema_version=1,**identity,model=None,session_id='session',status='completed',exit_code=False,summary='',error=None,usage=None,artifacts=[],truncated=False)
r=parse_agent_result(m.ProcessResult('completed',0,json.dumps(protocol).encode(),b'',.01,False,None,None),expected=identity)
results['boolean_exit_code']={'supplied_exit_code':False,'result':r.to_dict()}
Path('/tmp/m0r-review-evidence/probes.json').write_text(json.dumps(results,indent=2))
