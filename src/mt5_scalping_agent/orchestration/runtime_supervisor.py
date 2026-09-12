"""Durable, fail-closed supervision for long-running research workers."""
from __future__ import annotations
import hashlib,json,os,platform,shutil,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from typing import Sequence
SPEC_V12="12eb328ccc433a4dd75128fafdfb56fe293e30c96bc0962510554b218621610f"
TERMINAL={"SUCCEEDED","FAILED","INVALID"}; STATES={"CREATED","STARTING","RUNNING","CHECKPOINTED","COMPLETING",*TERMINAL}
def _now(): return datetime.now(timezone.utc).isoformat()
def _atomic_json(path:Path,value:dict)->None:
 path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp")
 with tmp.open("w",encoding="utf-8",newline="\n") as fh: json.dump(value,fh,indent=2,sort_keys=True);fh.write("\n");fh.flush();os.fsync(fh.fileno())
 os.replace(tmp,path)
def _sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as fh:
  for chunk in iter(lambda:fh.read(1048576),b""):h.update(chunk)
 return h.hexdigest()
def _state(run:Path,name:str,**updates)->dict:
 if name not in STATES:raise ValueError(name)
 p=run/"state.json";current=json.loads(p.read_text("utf-8")) if p.exists() else {};current.update(updates);current["state"]=name;current["updated_at"]=_now();_atomic_json(p,current);return current
def reserve_run(root:Path,*,run_id:str,task_id:str,specification_hash:str,code_commit:str,authorized_windows:Sequence[str],symbols:Sequence[str])->Path:
 if specification_hash!=SPEC_V12:raise ValueError("frozen v12 specification hash mismatch")
 if set(authorized_windows)!={"2019","2020","2021"}:raise ValueError("authority must be exactly 2019-2021")
 run=root/run_id;run.mkdir(parents=True,exist_ok=False)
 for d in ("staging","quarantine"):(run/d).mkdir()
 identity={"run_id":run_id,"task_id":task_id,"specification_hash":specification_hash,"code_commit":code_commit,"authorized_data_windows":list(authorized_windows),"authorized_symbols":list(symbols),"created_at":_now(),"environment":{"python":sys.version,"platform":sys.platform,"executable":sys.executable},"checkpoint_policy":"DISABLED_NO_PROVEN_V12_RNG_EQUIVALENCE_CLEAN_RERUN_ONLY"}
 _atomic_json(run/"identity.json",identity);_state(run,"CREATED",**identity);return run
def _usage(pid:int)->dict:
 try:
  import psutil
  p=psutil.Process(pid);return {"cpu_seconds":sum(p.cpu_times()[:2]),"rss_bytes":p.memory_info().rss,"child_pids":[c.pid for c in p.children(recursive=True)],"responsive":p.is_running()}
 except Exception:return {"cpu_seconds":None,"rss_bytes":None,"child_pids":[],"responsive":True}
def validate_and_publish(run:Path,required:Sequence[str])->dict:
 staging=run/"staging"
 sources={}
 for item in required:
  raw=str(item); source,name=(raw.split("::",1) if "::" in raw else (str(staging/raw),raw));sources[name]=Path(source)
 missing=[n for n,p in sources.items() if not p.is_file()]
 if missing:raise ValueError("missing mandatory artifacts: "+", ".join(missing))
 for name,source in sources.items():
  target=staging/name
  if source.resolve()!=target.resolve():shutil.copy2(source,target)
 hashes={n:_sha(staging/n) for n in sources};manifest={"validated_at":_now(),"artifacts":hashes,"specification_hash":SPEC_V12};_atomic_json(staging/"publication_manifest.json",manifest)
 committed=run/"evidence"
 if committed.exists():raise ValueError("evidence already published")
 os.replace(staging,committed);staging.mkdir();return manifest
def supervise(run:Path,command:Sequence[str],*,required_artifacts:Sequence[str],heartbeat_seconds:float=.2)->int:
 _state(run,"STARTING");out=open(run/"stdout.log","ab",buffering=0);err=open(run/"stderr.log","ab",buffering=0);started=_now()
 try:
  proc=subprocess.Popen(list(command),cwd=str(run/"staging"),stdout=out,stderr=err)
  _state(run,"RUNNING",pid=proc.pid,process_start=started,command=list(command),heartbeat_at=_now())
  while proc.poll() is None:_state(run,"RUNNING",pid=proc.pid,heartbeat_at=_now(),**_usage(proc.pid));time.sleep(heartbeat_seconds)
  code=proc.returncode;ended=_now()
  if code!=0:_state(run,"FAILED",exit_code=code,exit_timestamp=ended,termination_reason="WORKER_NONZERO_EXIT");return code
  _state(run,"COMPLETING",exit_code=code,exit_timestamp=ended)
  try:manifest=validate_and_publish(run,required_artifacts)
  except Exception as exc:
   q=run/"quarantine"/"failed-staging"
   if q.exists():shutil.rmtree(q)
   os.replace(run/"staging",q);(run/"staging").mkdir();_state(run,"INVALID",exit_code=code,termination_reason="MANDATORY_VALIDATION_OR_PUBLICATION_FAILURE",error=str(exc));return 3
  _state(run,"SUCCEEDED",exit_code=0,publication_manifest=manifest,termination_reason="VALIDATED_ATOMIC_PUBLICATION");return 0
 except BaseException as exc:_state(run,"FAILED",exit_code=None,exit_timestamp=_now(),termination_reason="SUPERVISOR_EXCEPTION",error=repr(exc));return 4
 finally:out.close();err.close()
def launch_detached(run:Path,command:Sequence[str],required_artifacts:Sequence[str])->int:
 _atomic_json(run/"launch.json",{"command":list(command),"required_artifacts":list(required_artifacts)})
 args=[sys.executable,"-m","mt5_scalping_agent.orchestration.runtime_supervisor","daemon",str(run)];flags=0
 if os.name=="nt":flags=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP
 with open(run/"supervisor.log","ab",buffering=0) as log:proc=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=log,close_fds=True,creationflags=flags,start_new_session=os.name!="nt")
 _atomic_json(run/"supervisor_identity.json",{"supervisor_pid":proc.pid,"launched_at":_now()});return proc.pid
def main(argv=None)->int:
 args=list(sys.argv[1:] if argv is None else argv)
 if len(args)!=2 or args[0]!="daemon":return 64
 run=Path(args[1]);cfg=json.loads((run/"launch.json").read_text("utf-8"));return supervise(run,cfg["command"],required_artifacts=cfg["required_artifacts"])
if __name__=="__main__":raise SystemExit(main())