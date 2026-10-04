"""Portable paths and atomic writes shared by records and automation."""
import os
import tempfile
from pathlib import Path, PureWindowsPath


def within(base: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('use a nonempty relative path with forward slashes')
    if Path(relative).is_absolute() or PureWindowsPath(relative).drive:
        raise ValueError('absolute/drive paths are not allowed')
    path = base / relative
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError(f'path must remain within {base.name}: {relative}')
    return path


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
