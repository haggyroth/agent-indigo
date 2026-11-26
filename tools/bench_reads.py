"""Times the emulator reads one decision tick makes (#383), so an optimisation is measured, not assumed.

    python tools/bench_reads.py [state.ss1]

Boots the ROM (optionally a saved state with a party) and reports the mean cost of each read, then of the typical tick's mix: read_state() x
`--state-calls` (the main loop, _log_tool, events.observe, the status line ... all re-read it).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def timeit(fn, n=300):
    fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t0) / n * 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state", nargs="?", help="a saved state with a party (default: boot the ROM)")
    ap.add_argument("--state-calls", type=int, default=6, help="read_state() calls per tick to price (default 6)")
    a = ap.parse_args()
    from game.mgba_core import NativeMGBAClient
    from game.memory_reader import LeafGreenReader
    with NativeMGBAClient(show_window=False) as m:
        if a.state:
            assert m.load_state_file(a.state), "could not load the state"
            m.tick(30)
        else:
            m.run_frames(600)
        r = LeafGreenReader(m)
        from game.constants import Addr
        rows = [("read32", lambda: m.read32(Addr.GMAIN_CALLBACK2)), ("read_range(600)", lambda: m.read_range(Addr.PARTY_DATA, 600)),
                ("read_range(33000) one PC box", lambda: m.read_range(Addr.PARTY_DATA, 33000)), ("detect_context()", r.detect_context),
                ("read_party()", r.read_party), ("read_state()", r.read_state), ("read_bag()", r.read_bag), ("read_boxes()", r.read_boxes),
                ("read_item_ball_tiles()", r.read_item_ball_tiles)]
        width = max(len(n) for n, _ in rows)
        for name, fn in rows:
            print(f"{name:<{width}}  {timeit(fn, 300 if 'boxes' not in name else 30):9.1f} µs")
        per_tick = timeit(r.read_state) * a.state_calls
        print(f"\n{a.state_calls} x read_state() per tick = {per_tick / 1000:.2f} ms  (the emulator runs a frame in ~{timeit(lambda: m.run_frames(1), 200) / 1000:.2f} ms)")


if __name__ == "__main__":
    main()
