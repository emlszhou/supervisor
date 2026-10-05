import json,hashlib,shutil,tempfile,os,subprocess,concurrent.futures
from pathlib import Path
from supervisor.workspace import snapshot as sn,bundle as bu
from supervisor.storage.intents import IntentStore
R=[]
def run(n,f):
 try:R.append({'probe':n,'observed':f()})
 except Exception as e:R.append({'probe':n,'exception':type(e).__name__,'message':str(e)})
with tempfile.TemporaryDirectory() as d:
 t=Path(d);r=t/'repo';r.mkdir()
 def git(*a):return subprocess.check_output(['git','-C',str(r),*a],stderr=subprocess.PIPE).decode().strip()
 git('init');git('config','user.email','x@example.invalid');git('config','user.name','x');(r/'.gitignore').write_text('sub\n');(r/'sub').mkdir();(r/'sub/x').write_text('inside');git('add','.gitignore');git('add','-f','sub/x');git('commit','-m','test');sha=git('rev-parse','HEAD');outside=t/'outside';outside.mkdir();(outside/'x').write_text('outside');shutil.rmtree(r/'sub');(r/'sub').symlink_to(outside,target_is_directory=True)
 run('snapshot_ignored_parentlink_read',lambda:sn.capture_snapshot(r,baseline_commit=sha)['files'])
 # Build trusted arbitrary canonical manifest with missing task and nested path.
 for name,files in [('missing_task',{}),('nested_manifest',{'docs/a.md':'0'*64})]:
  root=t/name;root.mkdir();manifest={'schema_version':1,'task_id':'x','baseline_commit':sha,'files':files};raw=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode();(root/'manifest.json').write_bytes(raw);run(name,lambda root=root,raw=raw:bu.verify_bundle(root,hashlib.sha256(raw).hexdigest()))
 db=t/'concurrent.sqlite';params=dict(task_id='t',run_id='r',attempt_id='a',kind='verification',bundle_sha256='0'*64,snapshot_sha256='1'*64)
 def reserve(i):
  s=IntentStore(db)
  try:return s.reserve('op',**params)['status']
  finally:s.close()
 run('sqlite_8_connections_same_binding',lambda:list(concurrent.futures.ThreadPoolExecutor(8).map(reserve,range(8))))
 # During source reads inject one deterministic mutation after first hash read.
 draft=t/'draft';draft.mkdir();task=json.loads(Path('/workspace/supervisor/handoffs/M1/v1/task-bundle/task.json').read_text());task.update(status='draft',baseline_commit=None)
 for name,v in [('task.json',task),('allowed_files.json',[]),('forbidden_files.json',[]),('verification.json',{'schema_version':1,'checks':[{'id':'x','kind':'project','argv':['true'],'cwd':'.','required':True}]})]:(draft/name).write_text(json.dumps(v))
 (draft/'requirements.md').write_text('initial');real=Path.read_bytes;count=[0]
 from unittest.mock import patch
 def reads(p):
  b=real(p)
  if p==draft/'requirements.md':
   count[0]+=1
   if count[0]==1:p.write_text('mutated')
  return b
 with patch.object(Path,'read_bytes',reads):run('freeze_source_mutation_success',lambda:bu.freeze_bundle(draft,t/'frozen',task_id=task['task_id'],baseline_commit=sha))
 run('verify_mutation_output',lambda:bu.verify_bundle(t/'frozen',hashlib.sha256(real(t/'frozen/manifest.json')).hexdigest()))
print(json.dumps(R,indent=2))
