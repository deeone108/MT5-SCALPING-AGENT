import argparse, json
from pathlib import Path
from .state import StateStore
from .task import validate_task
from .result import validate_result
from .gates import assert_data_access
from .validator import load_json
ROOT=Path(__file__).resolve().parents[3]; DEFAULT=ROOT/"governance/state/project_state.json"
def main(argv=None):
 p=argparse.ArgumentParser(prog="mt5-orchestrator"); p.add_argument("--state",default=str(DEFAULT)); sub=p.add_subparsers(dest="command",required=True)
 for name in ("status","tasks","gate-status","phase-status"): sub.add_parser(name)
 c=sub.add_parser("create-task"); c.add_argument("manifest")
 v=sub.add_parser("validate-task"); v.add_argument("manifest")
 r=sub.add_parser("validate-result"); r.add_argument("result"); r.add_argument("task")
 a=sub.add_parser("advance-phase"); a.add_argument("phase"); a.add_argument("evidence")
 args=p.parse_args(argv); state=StateStore(args.state).read()
 if args.command in {"status","phase-status"}: out=state
 elif args.command=="tasks": out={k:state[k] for k in ("active_tasks","completed_tasks","blocked_tasks")}
 elif args.command=="gate-status": out={"gates":state["gates"],"data_access":state["data_access"]}
 elif args.command in {"create-task","validate-task"}: out=validate_task(load_json(args.manifest)); assert_data_access(state,out,out["allowed_data_window"])
 elif args.command=="validate-result": out=validate_result(load_json(args.result),load_json(args.task),state)
 else:
  from .orchestrator import Orchestrator
  out=Orchestrator(args.state).advance_phase(args.phase,load_json(args.evidence))
 print(json.dumps(out,indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())