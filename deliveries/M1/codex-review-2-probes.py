"""Bounded independent M1 review probes; run with Python, no external services."""
import copy, hashlib, json, os, shutil, sqlite3, subprocess, tempfile
from pathlib import Path
from unittest.mock import patch
from supervisor.workspace import baseline as bl, snapshot as sn, bundle as bu
from supervisor.policy.changes import check_changes
from supervisor.storage.intents import IntentStore
RESULTS=[]
def result(name, fn):
    try: value=fn(); RESULTS.append({'probe':name,'observed':value})
    except Exception as e: RESULTS.append({'probe':name,'exception':type(e).__name__,'message':str(e)})
def git(r,*args):
    return subprocess.check_output(['git','-C',str(r),*args],stderr=subprocess.PIPE).decode().strip()
def repo(t):
    r=t/'repo';r.mkdir();git(r,'init');git(r,'config','user.email','probe@example.invalid');git(r,'config','user.name','Probe');(r/'a.txt').write_text('a');(r/'.gitignore').write_text('ignored\n.venv/\n');git(r,'add','.');git(r,'commit','-m','baseline');return r,git(r,'rev-parse','HEAD')
def digest(x):
    x['snapshot_sha256']=sn._snapshot_digest({k:v for k,v in x.items() if k!='snapshot_sha256'});return x
with tempfile.TemporaryDirectory(prefix='m1-probes-') as td:
 t=Path(td);r,sha=repo(t)
 (r/'sub').mkdir()
 result('baseline_git_subdirectory',lambda:bl.inspect_baseline(r/'sub'))
 (r/'ignored').write_text('controlled')
 result('snapshot_ignored_missing',lambda:'ignored' not in [x['path'] for x in sn.capture_snapshot(r,baseline_commit=sha)['files']])
 (r/'ignored').unlink()
 (r/'.supervisor').mkdir();(r/'.supervisor'/'artifact').write_text('cache')
 result('snapshot_nonignored_artifact_included',lambda:'.supervisor/artifact' in [x['path'] for x in sn.capture_snapshot(r,baseline_commit=sha)['files']])
 shutil.rmtree(r/'.supervisor')
 (r/'.venv').mkdir();(r/'.venv'/'python').symlink_to('/usr/bin/python3')
 result('baseline_valid_excluded_venv',lambda:bl.inspect_baseline(r))
 shutil.rmtree(r/'.venv')
 git(r,'rm','a.txt')
 result('snapshot_staged_baseline_deletion',lambda:sn.capture_snapshot(r,baseline_commit=sha)['deleted'])
 git(r,'restore','--source=HEAD','--staged','--worktree','a.txt')
 snap=sn.capture_snapshot(r,baseline_commit=sha)
 old=sn._sha256_file
 def mutate(p):
    value=old(p)
    if p.name=='a.txt':p.write_text('changed during capture')
    return value
 with patch.object(sn,'_sha256_file',mutate):result('capture_mutation_not_rejected',lambda:sn.capture_snapshot(r,baseline_commit=sha)['snapshot_sha256'])
 (r/'a.txt').write_text('a')
 (r/'sub'/'child.txt').write_text('inside');git(r,'add','sub');git(r,'commit','-m','nested');sha2=git(r,'rev-parse','HEAD')
 outside=t/'outside';outside.mkdir();(outside/'child.txt').write_text('OUTSIDE');shutil.rmtree(r/'sub');(r/'sub').symlink_to(outside,target_is_directory=True)
 result('snapshot_parent_symlink_reads_external',lambda:[x for x in sn.capture_snapshot(r,baseline_commit=sha2)['files'] if x['path']=='sub/child.txt'])
 (r/'sub').unlink();(r/'sub').mkdir();(r/'sub'/'child.txt').write_text('inside')
 (r/'a.txt').write_text('version https://git-lfs.github.com/spec/v1\noid sha256:'+ '0'*64+'\nsize 1\n');git(r,'add','a.txt');git(r,'commit','-m','LFS pointer')
 result('baseline_LFS_pointer_accepted',lambda:bl.inspect_baseline(r))
 before={'schema_version':1,'baseline_commit':sha,'files':[],'deleted':[]};digest(before)
 def policy(after,allowed=['**'],forbidden=[]):return check_changes(before,digest(after),allowed=allowed,forbidden=forbidden,max_changed_files=5,max_diff_lines=10,diff_lines=1)
 one=copy.deepcopy(before);one['files']=[{'path':'x.py','mode':'100644','sha256':'0'*64}]
 result('globstar_zero_segment_allowed',lambda:policy(copy.deepcopy(one),['**/*.py']))
 result('globstar_zero_segment_forbidden',lambda:policy(copy.deepcopy(one),['**'],['**/*.py']))
 forged=copy.deepcopy(one);forged['files']=[{'path':'x.py','mode':'bogus','sha256':'not-a-digest'},{'path':'X.py','mode':'100644','sha256':'0'*64}];forged['schema_version']=True
 result('policy_forged_case_type_mode_hash',lambda:policy(forged))
 bad=copy.deepcopy(snap);bad['files'][0]['path']=2;digest(bad)
 result('snapshot_invalid_path_exception',lambda:sn.assert_snapshot(r,bad))
 draft=t/'draft';draft.mkdir()
 task=json.loads(Path('/workspace/supervisor/handoffs/M1/v1/task-bundle/task.json').read_text());task.update(status='draft',baseline_commit=None)
 for name,value in [('task.json',task),('allowed_files.json',['../escape']),('forbidden_files.json',[]),('verification.json',{'schema_version':1,'checks':[{'id':'x','kind':'project','argv':['true'],'cwd':'.','required':True}]})]:(draft/name).write_text(json.dumps(value))
 (draft/'requirements.md').write_text('requirement');(draft/'extra.txt').write_text('extra')
 result('freeze_invalid_pattern_and_extra',lambda:bu.freeze_bundle(draft,t/'bundle',task_id=task['task_id'],baseline_commit=sha))
 result('freeze_drops_extra',lambda: not (t/'bundle'/'extra.txt').exists())
 (draft/'extra.txt').unlink();(draft/'allowed_files.json').write_text('[]')
 task['budgets']['max_repair_rounds']=0;(draft/'task.json').write_text(json.dumps(task))
 result('freeze_schema_valid_zero_repairs',lambda:bu.freeze_bundle(draft,t/'bundle-zero',task_id=task['task_id'],baseline_commit=sha))
 task['budgets']['max_repair_rounds']=1;(draft/'task.json').write_text(json.dumps(task))
 (draft/'nested').mkdir();(draft/'nested'/'extra.txt').write_text('extra')
 result('freeze_regular_directory',lambda:bu.freeze_bundle(draft,t/'bundle-nested',task_id=task['task_id'],baseline_commit=sha))
 shutil.rmtree(draft/'nested')
 # Output ancestor link, immediate parent is a real directory under that link.
 (t/'linked').symlink_to(outside,target_is_directory=True);(outside/'sub').mkdir()
 result('freeze_output_ancestor_link',lambda:bu.freeze_bundle(draft,t/'linked/sub/bundle',task_id=task['task_id'],baseline_commit=sha))
 # Existing hardlinked sidecar must be rejected before SQLite consumes it.
 db=t/'db.sqlite';store=IntentStore(db);store.close();victim=t/'victim';victim.write_bytes(b'');os.link(victim,Path(str(db)+'-journal'))
 result('sqlite_hardlinked_journal_accepted',lambda:IntentStore(db).close())
 result('sqlite_parent_ancestor_link',lambda:IntentStore(t/'linked/sub/intents.sqlite').close())
 db2=t/'rollback.sqlite';store=IntentStore(db2)
 real=store._conn
 class CommitFailure:
    def execute(self,sql,*args):
        if sql=='COMMIT':raise sqlite3.OperationalError('injected commit failure')
        return real.execute(sql,*args)
    def __getattr__(self,n):return getattr(real,n)
 store._conn=CommitFailure()
 kwargs=dict(task_id='t',run_id='r',attempt_id='a',kind='verification',bundle_sha256='0'*64,snapshot_sha256='1'*64)
 result('sqlite_commit_failure',lambda:store.reserve('op',**kwargs))
 result('sqlite_commit_failure_rollback',lambda:store.get('op'))
 store._conn=real;store.reserve('op',**kwargs);store._conn=CommitFailure()
 result('sqlite_complete_commit_failure',lambda:store.complete('op',attempt_id='a',bundle_sha256='0'*64,snapshot_sha256='1'*64,evidence_sha256='2'*64))
 result('sqlite_complete_rollback_status',lambda:store.get('op')['status']);store.close()
print(json.dumps(RESULTS,indent=2))
