"""What a scorecard needs to be comparable across runs (#378): which model / settings / code / ROM / fixture produced it. Light imports only."""
import hashlib
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_sha_cache: dict[str, str] = {}


def file_sha1(path) -> str:
    """SHA-1 of a file ('' when it is not there), cached for the process: the ROM is 16 MB and every scenario asks."""
    key = str(path)
    if key not in _sha_cache:
        try:
            h = hashlib.sha1()
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
            _sha_cache[key] = h.hexdigest()
        except OSError:
            _sha_cache[key] = ""
    return _sha_cache[key]


def git_state() -> dict:
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    try:
        return {"git_sha": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}
    except Exception:
        return {"git_sha": "", "git_dirty": None}


def provenance(sc) -> dict:
    import config
    fixture = (sc.start_state or sc.start_save or "")
    return {
        "model": config.MODEL_NAME, "temperature": config.TEMPERATURE, "max_tokens": config.MAX_TOKENS, "context_tokens": getattr(config, "CONTEXT_TOKENS", 0),
        "use_vision": config.USE_VISION, "enable_thinking": config.ENABLE_THINKING, "battle_style": config.BATTLE_STYLE,
        "llm_base_url_local": any(h in config.LLM_BASE_URL for h in ("localhost", "127.0.0.1", "::1")),     # (the URL itself may carry a token: not recorded)
        **git_state(),
        "rom_sha1": file_sha1(config.ROM_PATH), "fixture": Path(fixture).name if fixture else "", "fixture_sha1": file_sha1(fixture) if fixture else "",
        "python": sys.version.split()[0], "platform": platform.platform(terse=True),
    }
