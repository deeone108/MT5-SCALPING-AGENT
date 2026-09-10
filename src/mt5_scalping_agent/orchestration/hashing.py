import hashlib, json
from pathlib import Path
from typing import Any

def sha256_bytes(value: bytes) -> str: return hashlib.sha256(value).hexdigest()
def sha256_file(path: str | Path) -> str: return sha256_bytes(Path(path).read_bytes())
def sha256_canonical_text_file(path: str | Path) -> str:
    """Hash text with LF endings so Git autocrlf cannot invalidate a freeze."""
    return sha256_bytes(Path(path).read_bytes().replace(b"\r\n", b"\n"))
def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)+"\n").encode()
def sha256_json(value: Any) -> str: return sha256_bytes(canonical_json_bytes(value))