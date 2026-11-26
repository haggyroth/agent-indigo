"""Crash-safe file writes (#382): write beside the target, fsync, then rename over it, so a crash or Ctrl-C leaves the OLD file or the NEW one — never half of one.

`LongTermMemory.save` already did this for progress.json; run_log meta, the checkpoint pointer and the journal snapshots now share one implementation.
"""
import json
import os
import shutil
from pathlib import Path


def atomic_write_text(path, text: str) -> None:
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_json(path, obj, **dumps_kw) -> None:
    atomic_write_text(path, json.dumps(obj, **dumps_kw))


def atomic_copy(src, dst) -> None:
    """Copy a file so `dst` is replaced all at once."""
    dst = Path(dst)
    tmp = dst.with_name(f".{dst.name}.tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)
