"""Two cores on a virtual link cable (#363 prototype): the lockstep runs both without deadlock and keeps their frame counters equal."""
import os

import pytest

from game import link

ROM = os.path.expanduser(os.environ.get("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba"))


@pytest.mark.skipif(not (link.available() and os.path.exists(ROM)), reason="needs the link module (python -m game._mgba_link_build), the main binding and the ROM")
def test_two_linked_cores_run_in_lockstep_without_deadlock():
    with link.TwoCoreLink(ROM) as pair:
        for _ in range(12):                                       # many short runs: the thread handoff is where a deadlock would show
            pair.run(100, timeout_ms=15000)
        a, b = pair.frame_counters()
        assert a == b == 1200
        assert pair.sio_modes() == [2, 2]                         # the game's own boot code selected the multi-player (link cable) mode on both
