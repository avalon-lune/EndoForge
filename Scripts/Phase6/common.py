"""Small Phase 6 evidence helpers; missing evidence never means a pass."""
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite(value, name):
    require(type(value) in (int, float) and math.isfinite(value), f'Nonfinite/missing numeric evidence: {name}')
    return value


def passed(name, report):
    require(report.get('passed') is True, f'Missing/failed report: {name}')
    # Only Boolean check collections are interpreted here. Numeric diagnostics
    # belong in metrics and must be checked against explicit acceptance limits.
    for key, value in report.get('checks', {}).items():
        if isinstance(value, bool):
            require(value, f'Failed check: {name}.{key}')


def resolve_child(directory, name):
    directory = Path(directory).resolve()
    result = (directory / name).resolve()
    require(result.is_relative_to(directory), 'Evidence path escapes its directory: ' + str(name))
    return result


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
