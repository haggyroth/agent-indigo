"""Two emulator cores joined by a virtual link cable (#363 prototype): the building block for a trade partner.

`game/_mgba_link_build.py` compiles the host half of libmgba's SIO lockstep (an optional second extension: `python -m game._mgba_link_build`). A `TwoCoreLink` loads the ROM twice, attaches both
cores to the lockstep and steps them together — each in its own thread, coupled only through the lockstep callbacks, so one sleeps exactly while the other catches up.

This is the plumbing, not the trade: nothing here drives the game's Cable Club yet. Raw core handles only (the NativeMGBAClient / partner routine come next, see the issue).
"""
from __future__ import annotations

import os


class LinkError(RuntimeError):
    pass


def available() -> bool:
    """True when both compiled extensions import (the main binding and the link module)."""
    try:
        import game._mgba_link  # noqa: F401
        import game._mgba_native  # noqa: F401
    except Exception:
        return False
    return True


class TwoCoreLink:
    """Two cores running the same ROM, linked. Core 0 is the cable's master (the player who opens the link), core 1 the slave."""

    def __init__(self, rom_path: str):
        from game._mgba_link import lib as link
        from game._mgba_native import lib as native
        self._link, self._native = link, native
        if link.link_create() != 0:
            raise LinkError("a link already exists in this process (one at a time): close() it first")
        self.handles = [native.pycore_load(os.path.expanduser(rom_path).encode()) for _ in range(2)]
        if not all(self.handles):
            self.close()
            raise LinkError(f"could not load the ROM {rom_path}")
        for h in self.handles:
            native.pycore_reset(h)
        self.ids = [link.link_attach(h) for h in self.handles]
        if self.ids != [0, 1]:
            self.close()
            raise LinkError(f"could not attach both cores to the lockstep (ids {self.ids})")

    def run(self, frames: int, timeout_ms: int = 20000) -> None:
        """Advance both cores by `frames`. A timeout means the lockstep deadlocked (the threads are stopped and joined before this raises)."""
        if self._link.link_run(int(frames), int(timeout_ms)):
            raise LinkError(f"the link stalled after {self.frame_counters()} frames (deadlock)")

    def frame_counters(self) -> list[int]:
        return [self._link.link_frame_counter(i) for i in (0, 1)]

    def sio_modes(self) -> list[int]:
        """The serial mode each game has selected (libmgba GBASIOMode: 0 = Normal-8, 1 = Normal-32, 2 = Multi-player — the Cable Club link)."""
        return [self._link.link_mode(i) for i in (0, 1)]

    def close(self) -> None:
        self._link.link_destroy()
        for h in getattr(self, "handles", []):
            if h:
                self._native.pycore_destroy(h)
        self.handles = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
