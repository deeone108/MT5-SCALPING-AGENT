from pathlib import Path
import tomllib
ROOT=Path(__file__).resolve().parents[2]
def test_qa_tooling_provenance_and_interpreter_qualified_invocation():
 config=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))
 assert any(x.startswith('pytest>=8.0,<9') for x in config['project']['optional-dependencies']['dev'])
 doc=(ROOT/'governance/QA_TEST_ENVIRONMENT.md').read_text(encoding='utf-8')
 assert '.venv\\Scripts\\python.exe' in doc and '-m pytest' in doc and 'does not open market data' in doc
