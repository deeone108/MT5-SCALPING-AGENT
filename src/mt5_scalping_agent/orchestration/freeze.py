from datetime import datetime, timezone
from pathlib import Path
from .hashing import sha256_canonical_text_file
from .roles import require
from .validator import validate_hash

def freeze_experiment(*,role,specification_path,project_root,dataset_root,git_commit,phase,allowed_data,random_seeds,methodology_version):
    require(role,"FREEZE_SPEC"); validate_hash(dataset_root,64,"dataset_root"); validate_hash(git_commit,40,"git_commit")
    path=Path(specification_path); absolute=Path(project_root)/path
    return {"schema_version":1,"specification_path":path.as_posix(),"sha256":sha256_canonical_text_file(absolute),"dataset_root":dataset_root,"timestamp":datetime.now(timezone.utc).isoformat(),"git_commit":git_commit,"phase":phase,"allowed_data":[str(x) for x in allowed_data],"random_seeds":list(random_seeds),"methodology_version":methodology_version,"frozen":True}