from __future__ import annotations
import json,os,subprocess,sys,time
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
CODE=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
from mt5_scalping_agent.orchestration.runtime_supervisor import SPEC_V12,launch_detached,read_state,reserve_run,supervise,validate_and_publish

def reserve(tmp_path:Path,name="phase22b_test"):
 return reserve_run(tmp_path,repository=ROOT,run_id=name,task_id="PH22B-RI-002",specification_hash=SPEC_V12,code_commit=CODE,authorized_windows=["2019","2020","2021"],symbols=["EURUSD","GBPUSD","USDJPY","USDCAD"])
def state(run):return read_state(run)
def worker(code):return [sys.executable,"-c",code]
def test_stdout_survives_caller_interruption(tmp_path):
 r=reserve(tmp_path);assert supervise(r,worker("import pathlib;print('durable',flush=True);pathlib.Path('a').write_text('x')"),required_artifacts=["a"])==0;assert b"durable" in (r/"stdout.log").read_bytes()
def test_stderr_survives_caller_interruption(tmp_path):
 r=reserve(tmp_path);supervise(r,worker("import pathlib,sys;print('diagnostic',file=sys.stderr,flush=True);pathlib.Path('a').write_text('x')"),required_artifacts=["a"]);assert b"diagnostic" in (r/"stderr.log").read_bytes()
def test_exit_code_persisted(tmp_path):
 r=reserve(tmp_path);assert supervise(r,worker("raise SystemExit(7)"),required_artifacts=[])==7;assert state(r)["exit_code"]==7
def test_abnormal_death_failed(tmp_path):
 r=reserve(tmp_path);supervise(r,worker("import os;os._exit(9)"),required_artifacts=[]);assert state(r)["state"]=="FAILED"
def test_missing_result_never_success(tmp_path):
 r=reserve(tmp_path);assert supervise(r,worker("pass"),required_artifacts=["required.json"])==3;assert state(r)["state"]=="INVALID"
def test_partial_result_quarantined_not_evidence(tmp_path):
 r=reserve(tmp_path);supervise(r,worker("from pathlib import Path;Path('partial').write_text('x')"),required_artifacts=["missing"]);assert not (r/"evidence").exists();assert (r/"quarantine/invalid-staging/partial").exists()
def test_atomic_publication(tmp_path):
 r=reserve(tmp_path);(r/"staging/a").write_text("x");validate_and_publish(r,["a"]);assert (r/"evidence/a").exists();assert (r/"evidence/publication_manifest.json").exists()
def test_run_id_nonreuse(tmp_path):
 reserve(tmp_path)
 with pytest.raises(FileExistsError):reserve(tmp_path)
def test_spec_hash_recorded_and_validated(tmp_path):
 r=reserve(tmp_path);assert json.loads((r/"identity.json").read_text())["specification_hash"]==SPEC_V12
 with pytest.raises(ValueError):reserve_run(tmp_path,repository=ROOT,run_id="bad",task_id="x",specification_hash="0"*64,code_commit=CODE,authorized_windows=["2019","2020","2021"],symbols=[])
def test_code_commit_recorded(tmp_path):assert json.loads((reserve(tmp_path)/"identity.json").read_text())["code_commit"]==CODE
def test_authorized_window_recorded(tmp_path):assert json.loads((reserve(tmp_path)/"identity.json").read_text())["authorized_data_windows"]==["2019","2020","2021"]
@pytest.mark.parametrize("years",[["2022"],["2023"],["2024"],["2019","2020","2021","2024+"]])
def test_locked_forbidden_windows_rejected(tmp_path,years):
 with pytest.raises(ValueError):reserve_run(tmp_path,repository=ROOT,run_id="x",task_id="x",specification_hash=SPEC_V12,code_commit=CODE,authorized_windows=years,symbols=[])
def test_restart_cannot_broaden_authority(tmp_path):
 r=reserve(tmp_path);ident=(r/"identity.json").read_bytes();supervise(r,worker("raise SystemExit(1)"),required_artifacts=[]);assert (r/"identity.json").read_bytes()==ident
 with pytest.raises(FileExistsError):reserve(tmp_path)
def test_failed_artifacts_never_promoted(tmp_path):
 r=reserve(tmp_path);supervise(r,worker("from pathlib import Path;Path('a').write_text('x');raise SystemExit(2)"),required_artifacts=["a"]);assert not (r/"evidence").exists()
def test_monitor_interruption_does_not_own_worker_lifetime(tmp_path,monkeypatch):
 r=reserve(tmp_path);pid=launch_detached(r,worker("import pathlib,time;print('ok',flush=True);pathlib.Path('a').write_text('x')"),["a"]);assert pid>0
 for _ in range(100):
  if state(r)["state"] in {"SUCCEEDED","FAILED","INVALID"}:break
  time.sleep(.05)
 assert state(r)["state"]=="SUCCEEDED";assert b"ok" in (r/"stdout.log").read_bytes()
def test_checkpoint_resume_explicitly_disabled(tmp_path):assert json.loads((reserve(tmp_path)/"identity.json").read_text())["checkpoint_policy"].startswith("DISABLED_")
def test_identity_has_environment_process_and_timestamps(tmp_path):
 r=reserve(tmp_path);supervise(r,worker("from pathlib import Path;Path('a').write_text('x')"),required_artifacts=["a"]);s=state(r);assert s["process_start"] and s["exit_timestamp"] and s["pid"] and s["environment"]
def test_zero_exit_validation_failure_is_invalid(tmp_path):
 r=reserve(tmp_path);supervise(r,worker("pass"),required_artifacts=["x"]);assert state(r)["state"]=="INVALID"
def test_literal_non_json_mandatory_outputs_are_invalid_and_quarantined(tmp_path):
 r=reserve(tmp_path);code="from pathlib import Path;Path('development_artifact.json').write_text('not-json');Path('result_manifest.json').write_text('{}')"
 assert supervise(r,worker(code),required_artifacts=["development_artifact.json","result_manifest.json"])==3
 assert state(r)["state"]=="INVALID" and not (r/"evidence").exists()
 assert (r/"quarantine/invalid-staging/development_artifact.json").exists()

def test_reservation_rejects_code_symbol_and_window_drift(tmp_path):
 with pytest.raises(ValueError,match="code commit drift"):reserve_run(tmp_path,repository=ROOT,run_id="drift-code",task_id="PH22B-RI-002",specification_hash=SPEC_V12,code_commit="0"*40,authorized_windows=["2019","2020","2021"],symbols=["EURUSD","GBPUSD","USDJPY","USDCAD"])
 with pytest.raises(ValueError,match="symbol authority drift"):reserve_run(tmp_path,repository=ROOT,run_id="drift-symbol",task_id="PH22B-RI-002",specification_hash=SPEC_V12,code_commit=CODE,authorized_windows=["2019","2020","2021"],symbols=["EURUSD"])

def test_real_subprocess_caller_kill_preserves_detached_worker_and_provenance(tmp_path):
 r=reserve(tmp_path);launcher=tmp_path/"caller.py"
 launcher.write_text("import sys,time\nfrom pathlib import Path\nfrom mt5_scalping_agent.orchestration.runtime_supervisor import launch_detached\nr=Path(sys.argv[1])\nlaunch_detached(r,[sys.executable,'-c',\"import pathlib,time;print('survived',flush=True);time.sleep(.5);pathlib.Path('a').write_text('x')\"],['a'])\ntime.sleep(30)\n")
 env=dict(os.environ);env["PYTHONPATH"]=str(ROOT/"src")
 caller=subprocess.Popen([sys.executable,str(launcher),str(r)],env=env)
 for _ in range(100):
  if (r/"supervisor_identity.json").exists():break
  time.sleep(.03)
 caller.kill();caller.wait(timeout=5)
 for _ in range(200):
  if state(r)["state"] in {"SUCCEEDED","FAILED","INVALID"}:break
  time.sleep(.03)
 assert state(r)["state"]=="SUCCEEDED";assert b"survived" in (r/"stdout.log").read_bytes();assert (r/"evidence/a").exists()

def test_atomic_state_read_protocol_is_flake_safe_under_concurrency(tmp_path):
 import threading
 from mt5_scalping_agent.orchestration.runtime_supervisor import read_state
 r=reserve(tmp_path);errors=[]
 def reader():
  for _ in range(100):
   try:assert read_state(r)["state"] in {"CREATED","RUNNING"}
   except BaseException as exc:errors.append(exc)
 threads=[threading.Thread(target=reader) for _ in range(4)]
 for thread in threads:thread.start()
 from mt5_scalping_agent.orchestration.runtime_supervisor import _state
 for _ in range(100):_state(r,"RUNNING",heartbeat_at="2026-09-12T00:00:00+00:00")
 for thread in threads:thread.join()
 assert not errors

def test_stale_absent_worker_is_deterministically_invalid_and_quarantined(tmp_path):
 from mt5_scalping_agent.orchestration.runtime_supervisor import _state,reconcile
 r=reserve(tmp_path);(r/"staging/partial").write_text("x");_state(r,"RUNNING",pid=99999999,heartbeat_at="2000-01-01T00:00:00+00:00")
 assert reconcile(r,stale_seconds=0)["state"]=="INVALID";assert (r/"quarantine/orphaned-staging/partial").exists()

def test_reservation_canonicalizes_absolute_run_root_and_manifest_identity(tmp_path):
 r=reserve(tmp_path);identity=json.loads((r/"identity.json").read_text());assert r.is_absolute();assert identity["run_root"]==str(r);assert identity["run_id"]==r.name

def test_launch_manifest_and_supervisor_identity_share_absolute_run_root(tmp_path):
 r=reserve(tmp_path);pid=launch_detached(r,worker("from pathlib import Path;Path('a').write_text('x')"),["a"]);assert pid>0
 for _ in range(200):
  if state(r)["state"] in {"SUCCEEDED","FAILED","INVALID"}:break
  time.sleep(.03)
 launch=json.loads((r/"launch.json").read_text());identity=json.loads((r/"identity.json").read_text());supervisor=json.loads((r/"supervisor_identity.json").read_text())
 assert launch["run_root"]==identity["run_root"]==supervisor["run_root"]==str(r.resolve());assert launch["run_id"]==identity["run_id"]==supervisor["run_id"]==r.name

def test_windows_detached_supervisor_and_worker_survive_launcher_exit_then_record_native_failure(tmp_path):
 if os.name!="nt":pytest.skip("Windows process contract")
 r=reserve(tmp_path);launcher=tmp_path/"short_launcher.py"
 launcher.write_text("import sys\nfrom pathlib import Path\nfrom mt5_scalping_agent.orchestration.runtime_supervisor import launch_detached\nr=Path(sys.argv[1]).resolve()\ncmd=[sys.executable,'-c',\"import pathlib,sys,time;print('out',flush=True);print('err',file=sys.stderr,flush=True);stop=pathlib.Path('synthetic.stop');\\nwhile not stop.exists(): time.sleep(.05)\\nraise SystemExit(7)\"]\nlaunch_detached(r,cmd,[])\n",encoding="utf-8")
 env={key:os.environ[key] for key in ("SYSTEMROOT","TEMP","TMP") if key in os.environ};env["PYTHONPATH"]=str(ROOT/"src")
 caller=subprocess.Popen([sys.executable,str(launcher),str(r)],env=env,cwd=str(tmp_path));caller.wait(timeout=10);assert caller.returncode==0
 for _ in range(200):
  current=state(r)
  if current.get("state")=="RUNNING" and current.get("pid"):break
  time.sleep(.03)
 first=state(r);assert first["state"]=="RUNNING";worker_pid=first["pid"];supervisor_pid=json.loads((r/"supervisor_identity.json").read_text())["supervisor_pid"]
 def alive(pid):
  import ctypes
  handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,pid)
  if handle:ctypes.windll.kernel32.CloseHandle(handle)
  return bool(handle)
 assert alive(supervisor_pid) and alive(worker_pid);heartbeat=first["heartbeat_at"];time.sleep(.35);assert state(r)["heartbeat_at"]!=heartbeat
 assert b"out" in (r/"stdout.log").read_bytes();assert b"err" in (r/"stderr.log").read_bytes()
 (r/"staging/synthetic.stop").write_text("stop",encoding="utf-8")
 for _ in range(300):
  if state(r)["state"] in {"FAILED","INVALID"}:break
  time.sleep(.03)
 terminal=state(r);assert terminal["state"]=="FAILED";assert terminal["termination_reason"]=="WORKER_NONZERO_EXIT";assert terminal["exit_code"] is not None
 assert not (r/"evidence").exists()

def test_daemon_rejects_relative_or_mismatched_run_root(tmp_path):
 from mt5_scalping_agent.orchestration.runtime_supervisor import main
 assert main(["daemon","relative-run"])==65
 r=reserve(tmp_path);launch_detached(r,worker("from pathlib import Path;Path('a').write_text('x')"),["a"])
 for _ in range(200):
  if state(r)["state"] in {"SUCCEEDED","FAILED","INVALID"}:break
  time.sleep(.03)
 launch=json.loads((r/"launch.json").read_text());launch["run_id"]="wrong";(r/"launch.json").write_text(json.dumps(launch))
 assert main(["daemon",str(r)])==66


def test_windows_creation_contract_is_headless_breakaway_and_shell_free():
 from mt5_scalping_agent.orchestration.runtime_supervisor import _detached_creation_flags,_worker_creation_flags
 if os.name!="nt":pytest.skip("Windows process contract")
 assert _detached_creation_flags() & subprocess.CREATE_NO_WINDOW
 assert _detached_creation_flags() & subprocess.CREATE_NEW_PROCESS_GROUP
 assert _detached_creation_flags() & getattr(subprocess,"CREATE_BREAKAWAY_FROM_JOB",0x01000000)
 assert not (_detached_creation_flags() & subprocess.DETACHED_PROCESS)
 assert _worker_creation_flags() & subprocess.CREATE_NO_WINDOW

def test_launch_records_headless_shell_free_absolute_executable(tmp_path):
 r=reserve(tmp_path);pid=launch_detached(r,worker("from pathlib import Path;Path('a').write_text('x')"),["a"]);assert pid>0
 for _ in range(200):
  if state(r)["state"] in {"SUCCEEDED","FAILED","INVALID"}:break
  time.sleep(.03)
 launch=json.loads((r/"launch.json").read_text());supervisor=json.loads((r/"supervisor_identity.json").read_text())
 assert Path(launch["command"][0]).is_absolute();assert launch["shell"] is False;assert supervisor["shell"] is False
 if os.name=="nt":assert launch["windows_headless"] is True and supervisor["headless"] is True
 assert not any(Path(part).name.lower() in {"cmd.exe","powershell.exe","pwsh.exe"} for part in launch["command"])
 assert state(r)["worker_run_root"]==str(r.resolve())