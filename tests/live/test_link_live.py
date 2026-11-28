"""Two cores on a virtual link cable (#363): the lockstep runs both without deadlock, and the game's own Cable Club trades a Kadabra into an Alakazam between them."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from game import link

ROM = os.path.expanduser(os.environ.get("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba"))
ROOT = Path(__file__).resolve().parents[2]
needs_link = pytest.mark.skipif(not (link.available() and os.path.exists(ROM)), reason="needs the link module (python -m game._mgba_link_build), the main binding and the ROM")


@needs_link
def test_two_linked_cores_run_in_lockstep_without_deadlock():
    with link.TwoCoreLink(ROM) as pair:
        for _ in range(12):                                       # many short runs: the thread handoff is where a deadlock would show
            pair.run(100, timeout_ms=15000)
        a, b = pair.frame_counters()
        assert min(a, b) >= 1200 and abs(a - b) < 60              # a shared frame target: the counters stay together (a core may run a few frames on while its partner finishes a transfer)
        assert pair.sio_modes() == [2, 2]                         # the game's own boot code selected the multi-player (link cable) mode on both


@needs_link
def test_a_kadabra_trade_over_the_link_cable_evolves_into_alakazam(live, tmp_path):
    """Both players stand at the Viridian Pokémon Center 2F counter (the cable_club_counter recipe: Bulbasaur + Kadabra L30). The game's own Cable Club runs: link-up, seats, the trade screens, the
    trade evolution — nothing is written to memory but the staging."""
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "make_live_fixtures.py"), "--only", "cable_club_counter", "--out", str(tmp_path)],
                          capture_output=True, text=True, timeout=600, env={**os.environ, "LIVE_DIR": str(live.dir)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    with link.TwoCoreLink(ROM) as pair:
        pair.load_states(tmp_path / "cable_club_counter.ss1")
        assert pair.parties() == [[("Bulbasaur", 8), ("Kadabra", 30)]] * 2
        link.cable_club_trade(pair, give0=1, give1=1)
        assert pair.parties() == [[("Bulbasaur", 8), ("Alakazam", 30)]] * 2      # each side received a Kadabra, and a traded Kadabra evolves


@needs_link
def test_the_partner_trades_a_kadabra_back_as_an_alakazam_for_the_main_runtime(live, tmp_path):
    """The main runtime's own core (at the Pokémon Center 2F counter) is linked to a freshly loaded partner core: Kadabra goes over, evolves on the partner's side, and comes back for the Rattata it
    was traded for — then the link closes, the partner is gone and the main core steps on its own again."""
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "make_live_fixtures.py"), "--only", "cable_club_counter,partner_counter", "--out", str(tmp_path)],
                          capture_output=True, text=True, timeout=900, env={**os.environ, "LIVE_DIR": str(live.dir)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert live.m.load_state_file(str(tmp_path / "cable_club_counter.ss1"))
    live.m.tick(30)
    assert [(m.species_name, m.level) for m in live.r.read_party()] == [("Bulbasaur", 8), ("Kadabra", 30)]
    pair = link.TwoCoreLink.with_partner(live.m, ROM, str(tmp_path / "partner_counter.ss1"))
    try:
        link.trade_evolve(pair, give0=1, give1=1)
        partner_party = pair.parties()[1]
    finally:
        pair.close()
    assert [(m.species_name, m.level) for m in live.r.read_party()] == [("Bulbasaur", 8), ("Alakazam", 30)]
    assert partner_party == [("Bulbasaur", 8), ("Rattata", 5)]                       # the partner got its throwaway back
    assert tuple(live.r.read_current_map()) == (5, 5)
    frame = live.m.read32(0x030030F4)
    live.m.tick(30)
    assert live.m.read32(0x030030F4) == frame                                         # the main core runs alone again, on the field
