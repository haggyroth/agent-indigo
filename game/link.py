"""Two emulator cores joined by a virtual link cable (#363): the building block for a trade partner.

`game/_mgba_link_build.py` compiles the host half of libmgba's SIO lockstep (an optional second extension: `python -m game._mgba_link_build`). A `TwoCoreLink` loads the ROM twice, attaches both
cores to the lockstep and steps them together — each in its own thread, coupled only through the lockstep callbacks, so one sleeps exactly while the other catches up. Each core is a normal
`NativeMGBAClient` (with a `LeafGreenReader`), and its `run_frames` is replaced by the pair's, so anything that drives one client advances both.

`cable_club_trade` drives the game's own Cable Club from two states standing at the Pokémon Center 2F counter: link-up, the walk to the seats, the trade screens, the evolution scene. The
game does every step (the link protocol, the trade, the evolution); this only presses buttons, with the timing made deterministic by `press` (each core holds its keys for its OWN frames).
"""
from __future__ import annotations

import os

# GBA key bits (the same masks as game/mgba_core.py; not imported from it so this module loads where the compiled binding is absent, e.g. CI's unit-test jobs).
A, RIGHT, LEFT, UP, DOWN = 1 << 0, 1 << 4, 1 << 5, 1 << 6, 1 << 7
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

    def __init__(self, rom_path: str | None = None, clients: list | None = None):
        """Either `rom_path` (both cores are created here) or `clients` — two ready NativeMGBAClients (core 0 the master). A client passed in is NOT closed with the pair, and its own
        `run_frames` comes back on close (see with_partner)."""
        from game._mgba_link import lib as link
        from game.memory_reader import LeafGreenReader
        from game.mgba_core import NativeMGBAClient
        self._link = link
        if link.link_create() != 0:
            raise LinkError("a link already exists in this process (one at a time): close() it first")
        self.clients: list = []
        self._owned: list[bool] = []
        try:
            if clients is None:
                clients = [NativeMGBAClient(os.path.expanduser(rom_path), show_window=False) for _ in range(2)]
                self._owned = [True, True]
            else:
                self._owned = [False] * len(clients)
            self.clients = list(clients)
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

    @classmethod
    def with_partner(cls, main_client, partner_rom: str, partner_state: str) -> "TwoCoreLink":
        """Link a RUNNING client (the main runtime's) to a fresh partner core restored from `partner_state`. The partner is created and closed here; the main client is left as it was."""
        from game.mgba_core import NativeMGBAClient
        partner = NativeMGBAClient(os.path.expanduser(partner_rom), show_window=False)
        try:
            if not partner.load_state_file(str(partner_state)):
                raise LinkError(f"could not load the partner state {partner_state}")
            pair = cls(clients=[main_client, partner])
        except Exception:
            partner.close()
            raise
        pair._owned = [False, True]
        pair.run(30)
        return pair

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
        for c, owned in zip(self.clients, self._owned):
            c.__dict__.pop("run_frames", None)              # back to the client's own stepping
            if owned:
                c.close()                                   # the client owns its core (its __del__ would free it a second time)
        self.clients = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _cursor_moves(slot: int) -> list[int]:
    """The trade screen's party is a two-column grid: the keys that take the cursor from slot 0 to `slot`."""
    return [RIGHT] * (slot % 2) + [DOWN] * (slot // 2)


# The trade screen's cursor (decomp src/trade.c sCursorMoveDestinations): positions 0-5 are the player's party (two columns, row-major), 6-11 the partner's, 12 is Cancel. Per position, the
# destination lists for UP, DOWN, LEFT, RIGHT: the first one that holds a Pokémon (or Cancel) is taken, and none means position 0.
_CURSOR_MOVES = (
    ((4, 2, 12, 12, 0, 0), (2, 4, 12, 12, 0, 0), (7, 6, 1, 0, 0, 0), (1, 6, 7, 0, 0, 0)),
    ((5, 3, 12, 12, 0, 0), (3, 5, 12, 12, 0, 0), (0, 7, 6, 1, 0, 0), (6, 7, 0, 1, 0, 0)),
    ((0, 0, 0, 0, 0, 0), (4, 0, 0, 0, 0, 0), (9, 8, 7, 6, 0, 0), (3, 1, 0, 0, 0, 0)),
    ((1, 1, 1, 1, 0, 0), (5, 1, 1, 1, 0, 0), (2, 9, 8, 7, 0, 0), (8, 9, 6, 6, 0, 0)),
    ((2, 2, 2, 2, 0, 0), (0, 0, 0, 0, 0, 0), (11, 10, 9, 8, 7, 6), (5, 3, 1, 0, 0, 0)),
    ((3, 3, 3, 3, 0, 0), (1, 1, 1, 1, 0, 0), (4, 4, 4, 4, 0, 0), (10, 8, 6, 0, 0, 0)),
    ((10, 8, 12, 0, 0, 0), (8, 10, 12, 0, 0, 0), (1, 0, 0, 0, 0, 0), (7, 0, 1, 0, 0, 0)),
    ((12, 0, 0, 0, 0, 0), (9, 12, 0, 0, 0, 0), (6, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0)),
    ((6, 0, 0, 0, 0, 0), (10, 6, 0, 0, 0, 0), (3, 2, 1, 0, 0, 0), (9, 7, 0, 0, 0, 0)),
    ((7, 0, 0, 0, 0, 0), (11, 12, 0, 0, 0, 0), (8, 0, 0, 0, 0, 0), (2, 1, 0, 0, 0, 0)),
    ((8, 0, 0, 0, 0, 0), (6, 0, 0, 0, 0, 0), (5, 4, 3, 2, 1, 0), (11, 9, 7, 0, 0, 0)),
    ((9, 0, 0, 0, 0, 0), (12, 0, 0, 0, 0, 0), (10, 0, 0, 0, 0, 0), (4, 2, 0, 0, 0, 0)),
    ((11, 9, 7, 6, 0, 0), (7, 6, 0, 0, 0, 0), (12, 0, 0, 0, 0, 0), (12, 0, 0, 0, 0, 0)),
)
_CANCEL = 12


def _cursor_path(start: int, goal: int, own: int, other: int) -> list[int]:
    """The shortest key sequence on the trade screen from cursor position `start` to `goal`, with `own` Pokémon on the player's side and `other` on the partner's (breadth-first search over the
    game's own cursor table). A position holds something when it is Cancel or within the party counts."""
    active = {i for i in range(6) if i < own} | {6 + i for i in range(6) if i < other} | {_CANCEL}
    keys = (UP, DOWN, LEFT, RIGHT)
    seen, queue = {start: []}, [start]
    for pos in queue:
        if pos == goal:
            return seen[pos]
        for k, dests in zip(keys, _CURSOR_MOVES[pos]):
            new = next((d for d in dests if d in active), 0)
            if new not in seen:
                seen[new] = seen[pos] + [k]
                queue.append(new)
    raise LinkError(f"no way to move the trade cursor from {start} to {goal} ({own}/{other} Pokémon)")


def _poll_callbacks(pair: TwoCoreLink) -> list[int]:
    return [c.read32(0x030030F4) for c in pair.clients]


def enter_trade_room(pair: TwoCoreLink, max_presses: int = 300) -> None:
    """Both players stand at the Pokémon Center 2F counter (the `cable_club_counter` fixture): talk to the attendant, mash A through "Trade Center", the save prompt and the link-up until both are
    in the Trade Center room, walk to the two seats — (4,5) for the master, (7,5) for the slave; stepping onto a seat starts the trade link — and wait for the trade screen. Ends on it."""
    for _ in range(max_presses):
        if pair.maps() == [TRADE_CENTER, TRADE_CENTER]:
            break
        pair.press(A, A, hold=6, rest=24)
    else:
        raise LinkError(f"never reached the Trade Center (maps {pair.maps()})")
    pair.run(60)
    for _ in range(3):
        pair.press(UP, UP, hold=16, rest=4)
    pair.press(LEFT, RIGHT, hold=16, rest=4)
    pair.press(UP, UP, hold=16, rest=4)
    for _ in range(40):                                                          # "Communication standby…" until the trade screen is up on both
        pair.run(30)
        if all(cb == CB2_TRADE_SCREEN for cb in _poll_callbacks(pair)):
            break
    else:
        raise LinkError("the trade screen never came up")
    pair.run(600)                                                                # let the screen finish fading in and both sides settle before any input


def swap(pair: TwoCoreLink, give0: int, give1: int) -> None:
    """On the trade screen: trade party slot `give0` (0-based) of core 0 for `give1` of core 1 and sit through the animation and any evolution scene. The game then offers another trade, so the
    pair is left on the trade screen again. (Each side's received Pokémon takes the slot its own gave from.)"""
    # Pick: move the cursor, A (menu: SUMMARY / TRADE), Down, A (TRADE), A ("Is this trade okay?"), A on YES.
    moves0, moves1 = _cursor_moves(give0), _cursor_moves(give1)
    for i in range(max(len(moves0), len(moves1))):
        pair.press(moves0[i] if i < len(moves0) else 0, moves1[i] if i < len(moves1) else 0, hold=6, rest=40)
    pair.press(A, A, hold=6, rest=60)
    pair.press(DOWN, DOWN, hold=6, rest=30)
    pair.press(A, A, hold=6, rest=120)                                           # TRADE
    pair.press(A, A, hold=6, rest=120)                                           # "Is this trade okay?"
    pair.run(300)                                                                # …the YES / NO box only comes up after both players have asked
    pair.press(A, A, hold=6, rest=60)                                            # YES
    # The trade animation and the evolution scene (A advances their text), until both are back on the "Choose a POKéMON." screen.
    left = False
    for _ in range(120):
        pair.press(A, A, hold=6, rest=114)
        cbs = _poll_callbacks(pair)
        left = left or any(cb != CB2_TRADE_SCREEN for cb in cbs)
        if left and all(cb == CB2_TRADE_SCREEN for cb in cbs):
            return
    raise LinkError(f"the trade never finished (callbacks {[hex(cb) for cb in _poll_callbacks(pair)]})")


def leave_trade_room(pair: TwoCoreLink) -> None:
    """From the trade screen: the cursor to Cancel (the keys depend on the two party sizes), A, A ("Cancel trade?" YES), walk to the exit tiles — (5,8) and (6,8) — and Down once more ("The link will be terminated if you leave"), A through it: both
    are back on the Pokémon Center 2F floor and the link is closed by the game."""
    pair.run(600)                                                                # the screen has only just come back from the trade: let it finish drawing before any input
    counts = [len(p) for p in pair.parties()]                                    # a finished trade re-opens the screen with the cursor on slot 0
    paths = [_cursor_path(0, _CANCEL, counts[i], counts[1 - i]) for i in (0, 1)]
    for i in range(max(map(len, paths))):
        pair.press(*(p[i] if i < len(p) else 0 for p in paths), hold=6, rest=20)
    pair.press(A, A, hold=6, rest=150)                                           # "Cancel trade?"
    pair.press(A, A, hold=6, rest=150)                                           # YES
    for _ in range(40):                                                          # the screen fades out on both before the field is back (it can take a while: the link is closed in step)
        pair.run(60)
        if all(cb == CB2_OVERWORLD for cb in _poll_callbacks(pair)):
            break
    else:
        raise LinkError(f"the trade screen did not close (callbacks {[hex(cb) for cb in _poll_callbacks(pair)]})")
    pair.run(120)
    for _ in range(2):
        pair.press(DOWN, DOWN, hold=16, rest=4)
    pair.press(RIGHT, LEFT, hold=16, rest=4)
    pair.press(DOWN, DOWN, hold=16, rest=4)
    pair.press(DOWN, DOWN, hold=16, rest=30)                                     # onto the warp: "The link will be terminated if you leave"
    for _ in range(8):
        pair.press(A, A, hold=6, rest=150)
        if all(m != TRADE_CENTER for m in pair.maps()):                          # back upstairs in whichever Pokémon Center this is
            pair.run(300)
            return
    raise LinkError(f"never left the Trade Center (maps {pair.maps()})")


def cable_club_trade(pair: TwoCoreLink, give0: int = 1, give1: int = 1) -> None:
    """One trade, start to finish: enter the room, swap `give0` for `give1`, leave."""
    enter_trade_room(pair)
    swap(pair, give0, give1)
    leave_trade_room(pair)


def trade_evolve(pair: TwoCoreLink, give0: int, give1: int) -> None:
    """A trade evolution with a partner: the Pokémon only evolves on the RECEIVING side, so core 0's slot `give0` goes to the partner (in exchange for its slot `give1`, a throwaway), evolves
    there, and is traded back for the throwaway — both on the same two slots, in one visit to the room."""
    enter_trade_room(pair)
    swap(pair, give0, give1)
    swap(pair, give0, give1)
    leave_trade_room(pair)
