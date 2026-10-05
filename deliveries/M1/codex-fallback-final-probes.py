import concurrent.futures, copy, hashlib, json, os, sqlite3, subprocess, tempfile
from pathlib import Path
from unittest.mock import patch
from supervisor.workspace import snapshot as sn, baseline as bl, bundle as bu
from supervisor.policy.changes import check_changes
from supervisor.storage.intents import IntentStore
R=[]
def probe(name,fn):
 try: R.append(dict(name=name,result=fn(),exception=None))
 except Exception as e: R.append(dict(name=name,result=None,exception=type(e).__name__,message=str(e)))
def git(p,*args): return subprocess.check_output(['git','-C',str(p),*args],stderr=subprocess.PIPE).decode().strip()
def reject(fn):
 try: fn()
 except ValueError: return True
 return False
with tempfile.TemporaryDirectory() as td:
 t=Path(td);r=t/'repo';r.mkdir();git(r,'init');git(r,'config','user.name','Verifier');git(r,'config','user.email','verify@example.invalid');(r/'a').write_text('a');(r/'.gitignore').write_text('ignored\n');git(r,'add','.');git(r,'commit','-m','base');sha=git(r,'rev-parse','HEAD')
 probe('clean_baseline',lambda:bl.inspect_baseline(r)==sha)
 (r/'a').write_text('index-only dirty');git(r,'add','a');(r/'a').write_text('a');probe('index_only_dirty_rejected',lambda:reject(lambda:bl.inspect_baseline(r)));git(r,'restore','--source=HEAD','--staged','a')
 git(r,'update-index','--assume-unchanged','a');(r/'a').write_text('dirty');probe('reject_assume_unchanged_dirty',lambda:reject(lambda:bl.inspect_baseline(r)));(r/'a').write_text('a');git(r,'update-index','--no-assume-unchanged','a')
 git(r,'update-index','--skip-worktree','a');(r/'a').write_text('dirty');probe('reject_skip_worktree_dirty',lambda:reject(lambda:bl.inspect_baseline(r)));(r/'a').write_text('a');git(r,'update-index','--no-skip-worktree','a')
 git(r,'config','core.filemode','false');(r/'a').chmod(0o755);probe('reject_unreported_mode_dirty',lambda:reject(lambda:bl.inspect_baseline(r)));(r/'a').chmod(0o644)
 (r/'ignored').write_text('i');probe('ignored_controlled',lambda:any(f['path']=='ignored' for f in sn.capture_snapshot(r,baseline_commit=sha)['files']));(r/'ignored').unlink()
 (r/'.venv').mkdir();(r/'.venv/python').symlink_to('/usr/bin/python3');probe('excluded_links_ignored',lambda:bl.inspect_baseline(r)==sha)
 git(r,'rm','a');probe('baseline_staged_deletion',lambda:sn.capture_snapshot(r,baseline_commit=sha)['deleted']==['a']);git(r,'restore','--source=HEAD','--staged','--worktree','a')
 real=sn._read_regular
 def mutate(root,rel,sig):
  data=real(root,rel,sig)
  if rel=='a':(root/rel).write_text('changed')
  return data
 with patch.object(sn,'_read_regular',mutate):probe('snapshot_observed_mutation_rejected',lambda:reject(lambda:sn.capture_snapshot(r,baseline_commit=sha)))
 (r/'a').write_text('a');(r/'sub').mkdir();(r/'sub/x').write_text('x');git(r,'add','sub');git(r,'commit','-m','nested');sha2=git(r,'rev-parse','HEAD');import shutil;shutil.rmtree(r/'sub');(r/'sub').symlink_to(t);probe('parent_symlink_rejected',lambda:reject(lambda:sn.capture_snapshot(r,baseline_commit=sha2)));(r/'sub').unlink()
 (r/'a').write_text('version https://git-lfs.github.com/spec/v1\n');probe('lfs_rejected',lambda:reject(lambda:sn.capture_snapshot(r,baseline_commit=sha2)));(r/'a').write_text('a')
 before=dict(schema_version=1,baseline_commit=sha,files=[],deleted=[])
 def digest(d):d['snapshot_sha256']=sn._snapshot_digest({k:v for k,v in d.items() if k!='snapshot_sha256'});return d
 digest(before);after=copy.deepcopy(before);after['files']=[dict(path='x.py',mode='100644',sha256='0'*64)];digest(after)
 params=dict(allowed=['**'],forbidden=['**/*.py'],max_changed_files=2,max_diff_lines=3,diff_lines=1)
 probe('forbidden_globstar_root',lambda:reject(lambda:check_changes(before,after,**params)))
 bad=copy.deepcopy(after);bad['schema_version']=True;digest(bad);probe('forged_snapshot_bool_rejected',lambda:reject(lambda:check_changes(before,bad,**params)))
 task=json.loads(Path('/tmp/m1-fallback-contract/handoffs/M1/v1/task-bundle/task.json').read_text());task.update(status='draft',baseline_commit=None);task['budgets']['max_repair_rounds']=0;draft=t/'draft';draft.mkdir()
 for n,v in [('task.json',task),('allowed_files.json',[]),('forbidden_files.json',[]),('verification.json',dict(schema_version=1,checks=[dict(id='x',kind='project',argv=['true'],cwd='.',required=True)]))]: (draft/n).write_text(json.dumps(v))
 (draft/'requirements.md').write_text('r');(draft/'docs').mkdir();(draft/'docs/x').write_text('x');out=t/'out';h=bu.freeze_bundle(draft,out,task_id=task['task_id'],baseline_commit=sha)
 probe('bundle_all_nested_and_zero_budget',lambda:bu.verify_bundle(out,h)['files'].get('docs/x')==hashlib.sha256(b'x').hexdigest())
 (out/'extra').write_text('x');probe('bundle_extra_rejected',lambda:reject(lambda:bu.verify_bundle(out,h)));(out/'extra').unlink()
 # Different mutation trigger, source requirements.
 def bm(root,rel,sig):
  data=real(root,rel,sig)
  if rel=='requirements.md':(root/rel).write_text('changed')
  return data
 with patch.object(bu,'_read_regular',bm):probe('bundle_requirements_mutation_rejected',lambda:reject(lambda:bu.freeze_bundle(draft,t/'mutant2',task_id=task['task_id'],baseline_commit=sha)))
 for suffix in ('','-wal','-shm','-journal'):
  db=t/('unsafe'+suffix.replace('-',''));link=Path(str(db)+suffix);link.symlink_to(t/'absent');probe('sqlite_dangling_'+(suffix or 'db'),lambda db=db:reject(lambda:IntentStore(db)));link.unlink()
 db=t/'db';reserve=dict(task_id='t',run_id='r',attempt_id='a',kind='verification',bundle_sha256='0'*64,snapshot_sha256='1'*64)
 def worker(i):
  s=IntentStore(db)
  try:return s.reserve('op',**reserve)['status']
  finally:s.close()
 probe('sqlite_eight_connections',lambda:list(concurrent.futures.ThreadPoolExecutor(8).map(worker,range(8)))==['pending']*8)
 s=IntentStore(db);conn=s._conn
 class Fail:
  def execute(self,q,*a):
   if q=='COMMIT':raise RuntimeError('injected commit failure')
   return conn.execute(q,*a)
 s._conn=Fail()
 def rollback_reserve():
  try:s.reserve('fail',**reserve)
  except RuntimeError:pass
  return conn.execute("SELECT count(*) FROM intents WHERE operation_id='fail'").fetchone()[0]==0
 probe('sqlite_reserve_commit_rollback',rollback_reserve)
 def rollback_complete():
  try:s.complete('op',attempt_id='a',bundle_sha256='0'*64,snapshot_sha256='1'*64,evidence_sha256='2'*64)
  except RuntimeError:pass
  return conn.execute("SELECT status FROM intents WHERE operation_id='op'").fetchone()[0]=='pending'
 probe('sqlite_complete_commit_rollback',rollback_complete);s._conn=conn;s.close()
 # Preexisting hardlinked DB/sidecars.
 for suffix in ('','-wal','-shm','-journal'):
  db=t/('hard'+suffix.replace('-',''));peer=t/('peer'+suffix.replace('-',''));peer.write_text('x');link=Path(str(db)+suffix);os.link(peer,link);probe('sqlite_hardlink_'+(suffix or 'db'),lambda db=db:reject(lambda:IntentStore(db)));link.unlink()
 # Missing no-follow capabilities must fail honestly.
 capabilities=os.supports_dir_fd
 with patch.object(os,'supports_dir_fd',set()):probe('unsupported_os_rejected',lambda:reject(lambda:sn.capture_snapshot(r,baseline_commit=sha)))
 # Simulate case-insensitive lookup of existing root name with same inode.
 realstat=os.stat
 def casestat(path,*args,**kw):
  if path=='.GITIGNORE':path='.gitignore'
  return realstat(path,*args,**kw)
 with patch.object(os,'stat',casestat):probe('case_insensitive_storage_rejected',lambda:reject(lambda:sn.capture_snapshot(r,baseline_commit=sha)))
 # Gitlink in current index even with ignored working directory must fail.
 git(r,'update-index','--add','--cacheinfo','160000,'+sha+',module');probe('submodule_rejected',lambda:reject(lambda:sn.capture_snapshot(r,baseline_commit=sha)));git(r,'update-index','--force-remove','module')
 # Controlled ordinary hardlink and case collision.
 os.link(r/'a',r/'hard');probe('snapshot_hardlink_rejected',lambda:reject(lambda:sn.capture_snapshot(r,baseline_commit=sha)));(r/'hard').unlink()
 (r/'A').write_text('case');probe('snapshot_case_collision_rejected',lambda:reject(lambda:sn.capture_snapshot(r,baseline_commit=sha)));(r/'A').unlink()
 # Concurrent creator must retain bytes and must not be cleaned.
 race=t/'race';realmkdir=Path.mkdir
 def mkdir(path,*args,**kw):
  if path==race:
   realmkdir(path);(path/'owned').write_text('other creator')
  return realmkdir(path,*args,**kw)
 with patch.object(Path,'mkdir',mkdir):probe('bundle_output_race_rejected',lambda:reject(lambda:bu.freeze_bundle(draft,race,task_id=task['task_id'],baseline_commit=sha)))
 probe('bundle_output_race_preserved',lambda:(race/'owned').read_text()=='other creator')
 # Permission failure observed by injected no-follow open denial.
 realopen=os.open
 def denied(path,*args,**kw):
  if path=='a':raise PermissionError('injected denial')
  return realopen(path,*args,**kw)
 with patch.object(os,'open',denied), patch.object(os,'supports_dir_fd',capabilities|{denied}):probe('permission_failure_not_success',lambda:reject(lambda:sn.capture_snapshot(r,baseline_commit=sha)))
 # Every malformed canonical manifest field type must be rejected.
 mroot=t/'malicious';mroot.mkdir()
 for field,val in [('schema_version',True),('task_id',[]),('baseline_commit',1),('files',[])]:
  manifest=dict(schema_version=1,task_id='x',baseline_commit=sha,files={});manifest[field]=val;raw=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode();(mroot/'manifest.json').write_bytes(raw)
  probe('malicious_manifest_'+field,lambda raw=raw:reject(lambda:bu.verify_bundle(mroot,hashlib.sha256(raw).hexdigest())))
 # Repository config must not launch fsmonitor hooks/Agent commands.
 hook=t/'monitor';marker=t/'hook_executed';hook.write_text('#!/bin/sh\ntouch '+str(marker)+'\nprintf "token\\0"\n');hook.chmod(0o755);git(r,'config','core.fsmonitor',str(hook))
 # Snapshot also invokes ls-files; probe independently of missing nested baseline files.
 probe('git_fsmonitor_command_not_executed',lambda:(sn.capture_snapshot(r,baseline_commit=sha),not marker.exists())[1])
 # Clean filter can execute during Git status; baseline must avoid it.
 git(r,'restore','--source=HEAD','--worktree','sub/x');git(r,'config','core.fsmonitor','false');filtermarker=t/'filter_executed';filt=t/'clean_filter';filt.write_text('#!/bin/sh\ntouch '+str(filtermarker)+'\ncat\n');filt.chmod(0o755);git(r,'config','filter.probe.clean',str(filt));(r/'.gitattributes').write_text('a filter=probe\n');git(r,'add','.gitattributes');git(r,'commit','-m','attribute');
 if filtermarker.exists():filtermarker.unlink()
 (r/'a').write_text('modified then restored');(r/'a').write_text('a')
 probe('baseline_clean_filter_not_executed',lambda:(bl.inspect_baseline(r),not filtermarker.exists())[1])
print(json.dumps(R,indent=2))
