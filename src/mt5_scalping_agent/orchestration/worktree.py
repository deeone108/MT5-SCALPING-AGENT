import subprocess
from pathlib import Path
from .errors import OrchestrationError, WORKTREE_POLICY_DENIED

def _git(repo:Path,*args:str)->str:
    p=subprocess.run(["git","-C",str(repo),*args],text=True,capture_output=True)
    if p.returncode: raise OrchestrationError(WORKTREE_POLICY_DENIED,p.stderr.strip())
    return p.stdout.strip()
def inspect(path:str|Path)->dict:
    p=Path(path).resolve(); common=Path(_git(p,"rev-parse","--git-common-dir"));
    if not common.is_absolute(): common=(p/common).resolve()
    main=common.parent.resolve()
    return {"path":str(p),"branch":_git(p,"branch","--show-current"),"head":_git(p,"rev-parse","HEAD"),"clean":not bool(_git(p,"status","--porcelain")),"main_worktree":str(main),"is_main":p==main}
def assert_worker_worktree(path:str|Path):
    info=inspect(path)
    if info["is_main"] or info["branch"] in {"main","master"}: raise OrchestrationError(WORKTREE_POLICY_DENIED,"workers may not edit main directly")
    return info
def create(repo:str|Path,path:str|Path,branch:str,base:str):
    repo=Path(repo).resolve(); path=Path(path).resolve()
    if path.exists(): raise OrchestrationError(WORKTREE_POLICY_DENIED,"worktree path already exists")
    _git(repo,"worktree","add","-b",branch,str(path),base); return assert_worker_worktree(path)
def close(repo:str|Path,path:str|Path,preserve_failed:bool=False):
    info=assert_worker_worktree(path)
    if preserve_failed: return {**info,"preserved":True}
    if not info["clean"]: raise OrchestrationError(WORKTREE_POLICY_DENIED,"dirty worktree preserved for investigation")
    _git(Path(repo),"worktree","remove",str(Path(path).resolve())); return {**info,"preserved":False,"closed":True}