"""Durable, fail-closed supervision for long-running research workers."""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from typing import Sequence
SPEC_V12="12eb328ccc433a4dd75128fafdfb56fe293e30c96bc0962510554b218621610f"
BENCHMARK_SHA256="7bf5c078912545645132d88ab73bf17068d8633f07acc242f56121fc3ca504c5"
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
def read_state(run:Path,retries:int=50)->dict:
 p=run/"state.json"
 for attempt in range(retries):
  try:return json.loads(p.read_text("utf-8"))
  except (PermissionError,json.JSONDecodeError,FileNotFoundError):
   if attempt+1==retries:raise
   time.sleep(.01)
def _state(run:Path,name:str,**updates)->dict:
 if name not in STATES:raise ValueError(name)
 p=run/"state.json";current=read_state(run) if p.exists() else {};current.update(updates);current["state"]=name;current["updated_at"]=_now()
 for attempt in range(50):
  try:_atomic_json(p,current);break
  except PermissionError:
   if attempt==49:raise
   time.sleep(.01)
 return current
def _quarantine(run:Path,label:str)->None:
 staging=run/"staging";target=run/"quarantine"/label
 if target.exists():raise ValueError("quarantine target already exists")
 if staging.exists():os.replace(staging,target)
 staging.mkdir()
def reconcile(run:Path,stale_seconds:float=30.0)->dict:
 current=read_state(run)
 if current.get("state") in TERMINAL:return current
 stamp=current.get("heartbeat_at") or current.get("updated_at");age=(datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds()
 if age<=stale_seconds:return current
 pid=current.get("pid");alive=False
 try:
  import psutil
  alive=bool(pid and psutil.pid_exists(pid))
 except Exception:pass
 if alive:return current
 _quarantine(run,"orphaned-staging");return _state(run,"INVALID",exit_code=None,exit_timestamp=_now(),termination_reason="STALE_HEARTBEAT_WORKER_ABSENT")
def _canonical(value)->str:
 return hashlib.sha256((json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()).hexdigest()
def _authoritative(repository:Path,specification_hash:str,code_commit:str,authorized_windows:Sequence[str],symbols:Sequence[str])->dict:
 root=repository.resolve();state=json.loads((root/"governance/state/project_state.json").read_text("utf-8"));task=json.loads((root/"governance/tasks/PH22B-RI-002.json").read_text("utf-8"));spec=json.loads((root/"research/phase22b_spec_v12.json").read_text("utf-8"));benchmark=json.loads((root/"governance/evidence/PH22B_V12_EXACT_BENCHMARK.json").read_text("utf-8"))
 actual_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
 if len(code_commit)!=40 or any(c not in "0123456789abcdef" for c in code_commit):raise ValueError("invalid code commit")
 if actual_commit!=code_commit:raise ValueError("code commit drift")
 if _canonical(spec)!=specification_hash or task.get("required_spec_hash")!=specification_hash or state.get("research_spec_hash")!=specification_hash:raise ValueError("authoritative specification drift")
 if _canonical(benchmark)!=BENCHMARK_SHA256:raise ValueError("benchmark evidence drift")
 if task.get("required_dataset_hash")!=state.get("dataset_root_hash"):raise ValueError("dataset binding drift")
 if list(task.get("allowed_data_window",[]))!=list(authorized_windows) or list(state.get("allowed_data_windows",[]))!=list(authorized_windows):raise ValueError("window authority drift")
 if list(task.get("data_authorization",{}).get("symbols",[]))!=list(symbols):raise ValueError("symbol authority drift")
 return {"repository":str(root),"state_sha256":_canonical(state),"task_sha256":_canonical(task),"spec_sha256":_canonical(spec),"dataset_sha256":state["dataset_root_hash"],"task_id":task["task_id"],"authorization_id":task["data_authorization"]["authorization_id"],"benchmark_sha256":BENCHMARK_SHA256}
def reserve_run(root:Path,*,repository:Path,run_id:str,task_id:str,specification_hash:str,code_commit:str,authorized_windows:Sequence[str],symbols:Sequence[str])->Path:
 root=root.resolve()
 if specification_hash!=SPEC_V12:raise ValueError("frozen v12 specification hash mismatch")
 if set(authorized_windows)!={"2019","2020","2021"}:raise ValueError("authority must be exactly 2019-2021")
 binding=_authoritative(repository,specification_hash,code_commit,authorized_windows,symbols)
 if task_id!=binding["task_id"]:raise ValueError("task identity drift")
 run=(root/run_id).resolve();run.mkdir(parents=True,exist_ok=False)
 for d in ("staging","quarantine"):(run/d).mkdir()
 identity={"run_root":str(run),"run_id":run_id,"task_id":task_id,"specification_hash":specification_hash,"code_commit":code_commit,"authorized_data_windows":list(authorized_windows),"authorized_symbols":list(symbols),"created_at":_now(),"environment":{"python":sys.version,"platform":sys.platform,"executable":sys.executable},"checkpoint_policy":"DISABLED_NO_PROVEN_V12_RNG_EQUIVALENCE_CLEAN_RERUN_ONLY","authoritative_binding":binding}
 _atomic_json(run/"identity.json",identity);_state(run,"CREATED",**identity);return run
def _usage(pid:int)->dict:
 try:
  import psutil
  p=psutil.Process(pid);return {"cpu_seconds":sum(p.cpu_times()[:2]),"rss_bytes":p.memory_info().rss,"child_pids":[c.pid for c in p.children(recursive=True)],"responsive":p.is_running()}
 except Exception:return {"cpu_seconds":None,"rss_bytes":None,"child_pids":[],"responsive":True}
def _validate_scientific(run:Path,staging:Path)->None:
 from jsonschema import Draft202012Validator
 identity=json.loads((run/"identity.json").read_text("utf-8"));root=Path(identity["authoritative_binding"]["repository"]);values={}
 for name in ("development_artifact.json","result_manifest.json"):
  try:values[name]=json.loads((staging/name).read_text("utf-8"))
  except Exception as exc:raise ValueError(f"invalid JSON: {name}") from exc
 artifact,result=values["development_artifact.json"],values["result_manifest.json"]
 if not isinstance(artifact,dict) or not isinstance(result,dict):raise ValueError("mandatory JSON objects absent")
 Draft202012Validator(json.loads((root/"governance/RESULT_MANIFEST.schema.json").read_text("utf-8"))).validate(result)
 evidence=artifact.get("evidence");Draft202012Validator(json.loads((root/"governance/PHASE22B_EVIDENCE.schema.json").read_text("utf-8"))).validate(evidence)
 if artifact.get("specification_sha256")!=identity["specification_hash"] or artifact.get("dataset_root_sha256")!=identity["authoritative_binding"]["dataset_sha256"]:raise ValueError("artifact provenance binding mismatch")
 evidence_spec=evidence.get("specification_hash",evidence.get("specification_sha256"))
 if evidence_spec!=identity["specification_hash"] or evidence.get("research_run_id")!=identity["run_id"] or evidence.get("code_version")!=identity["code_commit"]:raise ValueError("evidence identity mismatch")
 if evidence.get("dataset_authorization_id")!=identity["authoritative_binding"]["authorization_id"]:raise ValueError("evidence authorization mismatch")
 if evidence.get("provenance_hashes",{}).get("dataset_root")!=identity["authoritative_binding"]["dataset_sha256"] or evidence.get("provenance_hashes",{}).get("implementation_benchmark")!=identity["authoritative_binding"]["benchmark_sha256"]:raise ValueError("evidence provenance mismatch")
 if evidence.get("actionable") is not False or evidence.get("strategy_eligible") is not False or evidence.get("trade_direction") is not None:raise ValueError("evidence became actionable")
 declared=artifact.get("canonical_sha256");copy=dict(artifact);copy.pop("canonical_sha256",None)
 if declared!=_canonical(copy):raise ValueError("artifact canonical hash mismatch")
 arts=result.get("artifacts",[])
 if (result.get("task_id")!=identity["task_id"] or len(arts)!=1 or arts[0].get("sha256")!=declared or result.get("specification_hash_used")!=identity["specification_hash"] or result.get("dataset_hash_used")!=identity["authoritative_binding"]["dataset_sha256"] or result.get("data_windows_accessed")!=identity["authorized_data_windows"]):raise ValueError("result manifest provenance mismatch")
def validate_and_publish(run:Path,required:Sequence[str])->dict:
 staging=run/"staging"
 sources={}
 for item in required:
  raw=str(item); source,name=(raw.split("::",1) if "::" in raw else (str(staging/raw),raw))
  if Path(name).name!=name or name in {"publication_manifest.json","identity.json"}:raise ValueError("invalid publication artifact name")
  sources[name]=Path(source)
 missing=[n for n,p in sources.items() if not p.is_file()]
 if missing:raise ValueError("missing mandatory artifacts: "+", ".join(missing))
 for name,source in sources.items():
  target=staging/name
  if source.resolve()!=target.resolve():shutil.copy2(source,target)
 if {"development_artifact.json","result_manifest.json"}<=set(sources):_validate_scientific(run,staging)
 identity=json.loads((run/"identity.json").read_text("utf-8"))
 if not isinstance(identity,dict):raise ValueError("malformed run identity")
 hashes={n:_sha(staging/n) for n in sources};manifest={"validated_at":_now(),"artifacts":hashes,"run_id":identity["run_id"],"task_id":identity["task_id"],"specification_hash":identity["specification_hash"],"code_commit":identity["code_commit"],"authorized_data_windows":identity["authorized_data_windows"],"authorized_symbols":identity["authorized_symbols"],"authoritative_binding":identity["authoritative_binding"]};_atomic_json(staging/"publication_manifest.json",manifest)
 committed=run/"evidence"
 if committed.exists():raise ValueError("evidence already published")
 os.replace(staging,committed);staging.mkdir();return manifest
def _worker_creation_flags() -> int:
 return getattr(subprocess,"CREATE_NO_WINDOW",0x08000000) if os.name=="nt" else 0
def supervise(run:Path,command:Sequence[str],*,required_artifacts:Sequence[str],heartbeat_seconds:float=.2)->int:
 run=run.resolve()
 _state(run,"STARTING");out=open(run/"stdout.log","ab",buffering=0);err=open(run/"stderr.log","ab",buffering=0);started=_now()
 try:
  proc=subprocess.Popen(list(command),cwd=str(run/"staging"),stdin=subprocess.DEVNULL,stdout=out,stderr=err,close_fds=True,creationflags=_worker_creation_flags(),shell=False)
  _state(run,"RUNNING",pid=proc.pid,process_start=started,command=list(command),worker_run_root=str(run),worker_headless=os.name=="nt",heartbeat_at=_now())
  while proc.poll() is None:_state(run,"RUNNING",pid=proc.pid,heartbeat_at=_now(),**_usage(proc.pid));time.sleep(heartbeat_seconds)
  code=proc.returncode;ended=_now()
  if code!=0:_quarantine(run,"failed-staging");_state(run,"FAILED",exit_code=code,exit_timestamp=ended,termination_reason="WORKER_NONZERO_EXIT");return code
  _state(run,"COMPLETING",exit_code=code,exit_timestamp=ended)
  try:manifest=validate_and_publish(run,required_artifacts)
  except Exception as exc:
   _quarantine(run,"invalid-staging");_state(run,"INVALID",exit_code=code,exit_timestamp=_now(),termination_reason="MANDATORY_VALIDATION_OR_PUBLICATION_FAILURE",error=str(exc));return 3
  _state(run,"SUCCEEDED",exit_code=0,publication_manifest=manifest,termination_reason="VALIDATED_ATOMIC_PUBLICATION");return 0
 except BaseException as exc:
  try:_quarantine(run,"supervisor-exception-staging")
  except Exception:pass
  _state(run,"FAILED",exit_code=None,exit_timestamp=_now(),termination_reason="SUPERVISOR_EXCEPTION",error=repr(exc));return 4
 finally:out.close();err.close()
def _detached_creation_flags() -> int:
 if os.name != "nt": return 0
 # Explicitly headless and independent of host console and kill-on-close job.
 return (getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) |
         subprocess.CREATE_NEW_PROCESS_GROUP |
         getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000))
def launch_detached(run:Path,command:Sequence[str],required_artifacts:Sequence[str])->int:
 run=run.resolve()
 identity=json.loads((run/"identity.json").read_text("utf-8"))
 if identity.get("run_root")!=str(run) or identity.get("run_id")!=run.name:raise ValueError("run root identity mismatch")
 command=[str(item) for item in command]
 _atomic_json(run/"launch.json",{"run_root":str(run),"run_id":run.name,"windows_headless":os.name=="nt","shell":False,"command":command,"required_artifacts":list(required_artifacts)})
 args=[sys.executable,"-m","mt5_scalping_agent.orchestration.runtime_supervisor","daemon",str(run)]
 flags=_detached_creation_flags()
 with open(run/"supervisor.log","ab",buffering=0) as log:proc=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=log,close_fds=True,creationflags=flags,start_new_session=os.name!="nt",env=dict(os.environ),shell=False)
 _atomic_json(run/"supervisor_identity.json",{"run_root":str(run),"run_id":run.name,"supervisor_pid":proc.pid,"headless":os.name=="nt","shell":False,"launched_at":_now()});return proc.pid
def main(argv=None)->int:
 args=list(sys.argv[1:] if argv is None else argv)
 if len(args)!=2 or args[0]!="daemon":return 64
 supplied=Path(args[1])
 if not supplied.is_absolute():return 65
 run=supplied.resolve();cfg=json.loads((run/"launch.json").read_text("utf-8"));identity=json.loads((run/"identity.json").read_text("utf-8"))
 if not isinstance(cfg,dict) or not isinstance(identity,dict):return 66
 if cfg.get("run_root")!=str(run) or cfg.get("run_id")!=run.name or identity.get("run_root")!=str(run) or identity.get("run_id")!=run.name:return 66
 return supervise(run,cfg["command"],required_artifacts=cfg["required_artifacts"])
if __name__=="__main__":raise SystemExit(main())
