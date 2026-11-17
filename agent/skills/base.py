"""What every skill mixin may assume about the emulator — in ONE place.

Skills used to ask `getattr(self.mgba, "wait_until_idle", None)` in 20 places because the legacy HTTP backend predates the
native binding's idle detector. The capability check now lives here; the legacy client has a no-op `wait_until_idle` too, so a
backend that lacks the method is a test fake, not a code path the skills must know about.
"""
import logging

logger = logging.getLogger("agent.skills")
_LOGGED: set = set()


def log_once(key: str, msg: str, *args) -> None:
    """Log a failure the code deliberately tolerates, once per kind — a silent `except: pass` hid them completely."""
    if key not in _LOGGED:
        _LOGGED.add(key)
        logger.warning(msg, *args, exc_info=True)


class SkillBase:
    def _wait_idle(self) -> None:
        """Let the game finish its text / animation before the next input (native backend; a no-op where unsupported)."""
        fn = getattr(self.mgba, "wait_until_idle", None)
        if fn:
            fn()
