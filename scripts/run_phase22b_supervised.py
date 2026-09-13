"""Launch unchanged Phase 22B v12 worker under detached durable supervision."""
from __future__ import annotations
import argparse,subprocess,sys
from pathlib import Path
from mt5_scalping_agent.orchestration.runtime_supervisor import SPEC_V12,launch_detached,reserve_run
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--repository",type=Path,default=Path.cwd());p.add_argument("--runtime-root",type=Path,required=True);p.add_argument("--run-id",required=True);a=p.parse_args();root=a.repository.resolve();commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
 runtime_root=a.runtime_root.resolve();run=reserve_run(runtime_root,repository=root,run_id=a.run_id,task_id="PH22B-RI-002",specification_hash=SPEC_V12,code_commit=commit,authorized_windows=["2019","2020","2021"],symbols=["EURUSD","GBPUSD","USDJPY","USDCAD"])
 private=(run/"staging").resolve()
 cmd=[sys.executable,str(root/"scripts/run_phase22b_development.py"),"--repository",str(root),"--output-root",str(private),"--supervisor-run-root",str(run),"--run-id",a.run_id,"--code-version",commit];artifact=private/"reports"/"phase22b"/a.run_id/"development_artifact.json";result=private/"governance"/"results"/"PH22B-RI-002.json";pid=launch_detached(run,cmd,[f"{artifact}::development_artifact.json",f"{result}::result_manifest.json"]);print(f"run={a.run_id} supervisor_pid={pid} state={run/'state.json'}");return 0
if __name__=="__main__":raise SystemExit(main())