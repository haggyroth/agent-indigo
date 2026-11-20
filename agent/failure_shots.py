"""Save the screen when a tool fails (pure heuristics + a small limiter; the client does the I/O).

A watched run's PC skill said "The PC didn't open the storage screen" six times and the run log held no picture of what WAS on screen, so the cause could not be found afterwards. When a
tool's result reads like a failure, the client writes the current frame to `<run dir>/shots/<seconds>_<tool>.png` and records the path in that tool's run-log event (`shot`)."""
import re

_FAILURE = re.compile(
    r"^(Couldn't|Could not|Couldn’t|Stuck|Stopped at|Can't reach|Blocked|No route|Open the PC from)"
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
