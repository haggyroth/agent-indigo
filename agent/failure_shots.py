"""Save the screen when a tool fails (pure heuristics + a small limiter; the client does the I/O).

A watched run's PC skill said "The PC didn't open the storage screen" six times and the run log held no picture of what WAS on screen, so the cause could not be found afterwards. When a
tool's result reads like a failure, the client writes the current frame to `<run dir>/shots/<seconds>_<tool>.png` and records the path in that tool's run-log event (`shot`)."""
import re

_FAILURE = re.compile(
    r"^(Couldn't|Could not|Couldn’t|Stuck|Stopped at|Can't reach|Blocked|No route|No walkable|Open the PC from)"
    r"|\b(didn't|did not) (open|go through|start|take|work|respond|resolve|finish)\b"
    r"|\bwas stopped: no progress\b"
    r"|: stuck at\b|\bcould not cross\b",
    re.I)
MAX_SHOTS = 40            # per run: the point is a handful of clues, not a video
MIN_GAP_S = 5.0           # between any two shots
SAME_RESULT_GAP_S = 60.0  # the same tool failing the same way again (a retry loop) is one picture


def looks_like_failure(result) -> bool:
    return bool(_FAILURE.search(str(result or "").strip()[:300]))


def should_save(log: dict, tool: str, result, now: float) -> bool:
    """Decide (and record) whether this failure gets a picture. `log` is the per-run state dict: {"n": count, "last": time, "seen": {(tool, result prefix): time}}."""
    if not looks_like_failure(result):
        return False
    key = (tool, str(result).strip()[:50])
    if log.get("n", 0) >= MAX_SHOTS or now - log.get("last", -1e9) < MIN_GAP_S or now - log.get("seen", {}).get(key, -1e9) < SAME_RESULT_GAP_S:
        return False
    log["n"] = log.get("n", 0) + 1
    log["last"] = now
    log.setdefault("seen", {})[key] = now
    return True


STALL_REPEATS = 5         # the same tool failing the same way this many times in a row is a stall worth a snapshot
MAX_STALLS = 8            # emulator states saved per run (each is ~0.5 MB)


def _norm(result) -> str:
    """The result with its numbers blanked, so 'No walkable path from (12,117)' and '(13,110)' read as the same failure."""
    return re.sub(r"\d+", "N", " ".join(str(result or "").split()))[:90]


def note_stall(log: dict, tool: str, result) -> bool:
    """Record one tool result; True exactly when it is the STALL_REPEATS-th identical failing result in a row (and the run still has snapshot budget). The caller then saves an emulator
    state under `<run dir>/stalls/` — a real fixture of the stall, which logs alone could not give us (Route 23's phantom 'North edge' loop could not be reproduced from the logs)."""
    if not looks_like_failure(result):
        log["key"], log["run"] = None, 0
        return False
    key = (tool, _norm(result))
    log["run"] = log.get("run", 0) + 1 if log.get("key") == key else 1
    log["key"] = key
    if log["run"] != STALL_REPEATS or log.get("n", 0) >= MAX_STALLS:
        return False
    log["n"] = log.get("n", 0) + 1
    return True
