"""Two emulator cores joined by a virtual link cable (#363): the building block for a trade partner.

`game/_mgba_link_build.py` compiles the host half of libmgba's SIO lockstep (an optional second extension: `python -m game._mgba_link_build`). A `TwoCoreLink` loads the ROM twice, attaches both
cores to the lockstep and steps them together — each in its own thread, coupled only through the lockstep callbacks, so one sleeps exactly while the other catches up. Each core is a normal
`NativeMGBAClient` (with a `LeafGreenReader`), and its `run_frames` is replaced by the pair's, so anything that drives one client advances both.

`cable_club_trade` drives the game's own Cable Club from two states standing at the Pokémon Center 2F counter: link-up, the walk to the seats, the trade screens, the evolution scene. The
game does every step (the link protocol, the trade, the evolution); this only presses buttons, with the timing made deterministic by `press` (each core holds its keys for its OWN frames).
"""
from __future__ import annotations

import os

from game.mgba_core import _mask

A, UP, DOWN, LEFT, RIGHT = (_mask([b]) for b in ("A", "Up", "Down", "Left", "Right"))
TRADE_CENTER = (0, 1)
CB2_OVERWORLD = 0x080565B5                       # gMain.callback2 on the free field
CB2_TRADE_SCREEN = 0x0804D639                    # gMain.callback2 while the "Choose a POKéMON." trade screen is up (this LeafGreen build)


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
        from game.memory_reader import LeafGreenReader
        from game.mgba_core import NativeMGBAClient
        self._link = link
        if link.link_create() != 0:
            raise LinkError("a link already exists in this process (one at a time): close() it first")
        self.clients: list = []
        try:
            self.clients = [NativeMGBAClient(os.path.expanduser(rom_path), show_window=False) for _ in range(2)]
            self.ids = [link.link_attach(c._h) for c in self.clients]
        except Exception:
            self.close()
            raise
        if self.ids != [0, 1]:
            self.close()
            raise LinkError(f"could not attach both cores to the lockstep (ids {self.ids})")
        self.readers = [LeafGreenReader(c) for c in self.clients]
        for c in self.clients:
            c.run_frames = self.run                         # a tap / hold / tick on either client steps the whole pair

    def load_states(self, path0: str, path1: str | None = None) -> None:
        """Restore a saved state on each core (the second defaults to the first's: two copies of one player)."""
        for c, path in zip(self.clients, (path0, path1 or path0)):
            if not c.load_state_file(str(path)):
                raise LinkError(f"could not load the state {path}")
        self.run(30)

    def run(self, frames: int, timeout_ms: int = 20000) -> None:
        """Advance both cores by `frames` (to one shared frame count). A timeout means the lockstep deadlocked (the threads are stopped and joined before this raises)."""
        self.press(0, 0, hold=0, rest=frames, timeout_ms=timeout_ms)

    def press(self, keys0: int = 0, keys1: int = 0, hold: int = 6, rest: int = 24, timeout_ms: int = 20000) -> None:
        """One input step: core 0 holds `keys0` and core 1 `keys1` for their own first `hold` frames, then both run on to `hold + rest` frames in all."""
        if self._link.link_run_keys(int(hold + rest), int(timeout_ms), int(keys0), int(keys1), int(hold)):
            raise LinkError(f"the link stalled after {self.frame_counters()} frames (deadlock; SIO modes {self.sio_modes()})")

    def frame_counters(self) -> list[int]:
        return [self._link.link_frame_counter(i) for i in (0, 1)]

    def sio_modes(self) -> list[int]:
        """The serial mode each game has selected (libmgba GBASIOMode: 0 = Normal-8, 1 = Normal-32, 2 = Multi-player — the Cable Club link)."""
        return [self._link.link_mode(i) for i in (0, 1)]

    def maps(self) -> list[tuple]:
        return [tuple(r.read_current_map()) for r in self.readers]

    def parties(self) -> list[list[tuple]]:
        """[(species, level), …] for each core's party."""
        return [[(m.species_name, m.level) for m in r.read_party()] for r in self.readers]

    def close(self) -> None:
        self._link.link_destroy()
        for c in self.clients:
            c.close()                                       # the client owns its core (its __del__ would free it a second time)
        self.clients = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _cursor_moves(slot: int) -> list[int]:
    """The trade screen's party is a two-column grid: the keys that take the cursor from slot 0 to `slot`."""
    return [RIGHT] * (slot % 2) + [DOWN] * (slot // 2)


def cable_club_trade(pair: TwoCoreLink, give0: int = 1, give1: int = 1, max_presses: int = 300) -> None:
    """Both players stand at the Pokémon Center 2F counter (the `cable_club_counter` fixture): link up, sit down, trade party slot `give0` (0-based) of core 0 for `give1` of core 1, and sit through
    the evolution scene. The pair is left on the trade screen again (the game offers another trade). Raises LinkError when a stage does not come."""
    # 1. Talk to the attendant and mash A through "Trade Center", the save prompt and the link-up until both games are in the Trade Center room (map 0,1).
    for _ in range(max_presses):
        if pair.maps() == [TRADE_CENTER, TRADE_CENTER]:
            break
        pair.press(A, A, hold=6, rest=24)
    else:
        raise LinkError(f"never reached the Trade Center (maps {pair.maps()})")
    # 2. Walk to the two seats — (4,5) for the master, (7,5) for the slave; stepping onto a seat starts the trade link.
    pair.run(60)
    for _ in range(3):
        pair.press(UP, UP, hold=16, rest=4)
    pair.press(LEFT, RIGHT, hold=16, rest=4)
    pair.press(UP, UP, hold=16, rest=4)
    for _ in range(40):                                                          # "Communication standby…" until the trade screen is up on both
        pair.run(30)
        if all(c.read32(0x030030F4) == CB2_TRADE_SCREEN for c in pair.clients):
            break
    else:
        raise LinkError("the trade screen never came up")
    pair.run(600)                                                                # let the screen finish fading in and both sides settle before any input
    # 3. Pick the Pokémon: move the cursor, A (menu: SUMMARY / TRADE), Down, A (TRADE), A ("Is this trade okay?"), A on YES.
    moves0, moves1 = _cursor_moves(give0), _cursor_moves(give1)
    for i in range(max(len(moves0), len(moves1))):
        pair.press(moves0[i] if i < len(moves0) else 0, moves1[i] if i < len(moves1) else 0, hold=6, rest=40)
    pair.press(A, A, hold=6, rest=60)
    pair.press(DOWN, DOWN, hold=6, rest=30)
    pair.press(A, A, hold=6, rest=120)                                           # TRADE
    pair.press(A, A, hold=6, rest=120)                                           # "Is this trade okay?"
    pair.run(300)                                                                # …the YES / NO box only comes up after both players have asked
    pair.press(A, A, hold=6, rest=60)                                            # YES
    # 4. The trade animation and the evolution scene (A advances their text), until both games are back on the "Choose a POKéMON." screen — the game offers another trade.
    left = False
    for _ in range(120):
        pair.press(A, A, hold=6, rest=114)
        cbs = [c.read32(0x030030F4) for c in pair.clients]
        left = left or any(cb != CB2_TRADE_SCREEN for cb in cbs)
        if left and all(cb == CB2_TRADE_SCREEN for cb in cbs):
            return
    raise LinkError(f"the trade never finished (callbacks {[hex(c.read32(0x030030F4)) for c in pair.clients]})")
