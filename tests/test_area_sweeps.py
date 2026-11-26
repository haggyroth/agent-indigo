"""Area completion read from the game's flags (#366): the generated data pinned to the decomp, the progress logic, the observation line and the quest listing."""
import re
from types import SimpleNamespace

import pytest

from knowledge import sweeps
from knowledge.area_sweeps import AREAS

# (trainers, items, hidden) per area, as generated from the pret/pokefirered decomp (tools/gen_area_sweeps.py): a regeneration that changes these is a real change to look at.
COUNTS = {
    "Viridian Forest": (5, 4, 2), "Mt. Moon": (11, 10, 2), "Rock Tunnel": (15, 5, 0), "S.S. Anne": (16, 7, 4), "Rocket Hideout": (11, 12, 4), "Pokémon Tower": (16, 8, 2),
    "Silph Co.": (30, 17, 12), "Pokémon Mansion": (7, 12, 3), "Power Plant": (0, 7, 2), "Seafoam Islands": (0, 5, 2), "Safari Zone": (0, 12, 2), "Victory Road": (12, 8, 10),
    "Cerulean Gym": (2, 0, 0), "Vermilion Gym": (3, 0, 0), "Celadon Gym": (7, 0, 0), "Fuchsia Gym": (6, 0, 0), "Saffron Gym": (7, 0, 0), "Cinnabar Gym": (7, 0, 0),
    "Viridian Gym": (8, 0, 1), "Routes 2-4, Viridian, Pewter, Cerulean": (9, 4, 6), "Routes 24-25": (15, 2, 5), "Routes 9-10": (15, 2, 8),
    "Routes 6-8, Saffron, Vermilion": (18, 0, 7), "Routes 11-15, Fuchsia": (50, 6, 8), "Routes 16-18, Celadon (Cycling Road)": (20, 1, 7), "Routes 19-21": (30, 0, 0),
    # the Sevii Islands (#360); the Icefall Cave grunts and the Trainer Tower's trainers are scripted / built at run time, not object events, so they are not counted
    "Kindle Road / Mt. Ember": (16, 6, 2), "Two-Three Island (Cape Brink, Bond Bridge, Berry Forest)": (6, 5, 5), "Four Island / Icefall Cave": (0, 6, 0),
    "Five Island region": (22, 12, 5), "Six Island region": (29, 6, 4), "Seven Island region": (16, 4, 2), "Cerulean Cave": (0, 8, 1),
}


def test_the_generated_counts_match_the_decomp():
    assert {a: (len(d["trainers"]), len(d["items"]), len(d["hidden"])) for a, d in AREAS.items()} == COUNTS


def test_flags_are_distinct_in_range_and_trainer_flags_sit_in_the_trainer_block():
    seen = set()
    for area, d in AREAS.items():
        assert d["maps"], area
        for f in d["trainers"]:
            assert 0x500 <= f <= 0x7FF, (area, f)                      # TRAINER_FLAGS_START .. END
        for f in d["hidden"]:
            assert 1000 <= f < 1200, (area, f)                         # FLAG_HIDDEN_ITEMS_START ..
        for f in d["items"]:
            assert 0 < f < 0x800, (area, f)
        for kind in ("trainers", "items", "hidden"):
            for f in d[kind]:
                assert (kind, f) not in seen, (area, kind, f)          # an area never double-counts another's flag
                seen.add((kind, f))


def test_no_map_belongs_to_two_areas_and_known_flags_are_where_the_decomp_puts_them():
    maps = [m for d in AREAS.values() for m in d["maps"]]
    assert len(maps) == len(set(maps))
    assert sweeps.area_of_map((1, 1)) is None or sweeps.area_of_map((1, 1)) in AREAS
    assert 0x500 + 109 in sum((d["trainers"] for d in AREAS.values()), [])        # TRAINER_BUG_CATCHER_ROBBY (Mt. Moon 1F) = id 109 -> flag 0x56D
    assert 1002 in AREAS["Mt. Moon"]["hidden"] and 1084 not in AREAS["Mt. Moon"]["hidden"]    # the Moon Stone is a one-time find; the mushrooms respawn daily and are left out


def test_progress_counts_flags_and_formats_one_line():
    some = set(AREAS["Mt. Moon"]["trainers"][:4]) | set(AREAS["Mt. Moon"]["items"][:1])
    p = sweeps.progress("Mt. Moon", lambda f: f in some)
    assert p == {"trainers": (4, 11), "items": (1, 10), "hidden": (0, 2)}
    assert sweeps.line("Mt. Moon", p) == "Mt. Moon: 4/11 trainers, 1/10 items, 0/2 hidden items"
    assert sweeps.line("Cerulean Gym", sweeps.progress("Cerulean Gym", lambda f: False)) == "Cerulean Gym: 0/2 trainers"        # kinds the area lacks are omitted
    assert sweeps.remaining(p) == 7 + 9 and sweeps.remaining(p, hidden=True) == 7 + 9 + 2
    assert not sweeps.complete(p) and sweeps.complete(sweeps.progress("Mt. Moon", lambda f: True))


def test_started_lists_only_half_finished_areas_most_complete_first():
    done = set(AREAS["Cerulean Gym"]["trainers"][:1]) | set(AREAS["Viridian Forest"]["trainers"]) | set(AREAS["Viridian Forest"]["items"][:2])
    started = sweeps.started(lambda f: f in done)
    assert [a for a, _ in started] == ["Viridian Forest", "Cerulean Gym"]                # 7/11 beats 1/2; an untouched area is not 'started'
    assert sweeps.started(lambda f: False) == []


def test_the_s_s_anne_warning_exists_until_the_captain_has_given_cut():
    p = sweeps.progress("S.S. Anne", lambda f: False)
    note = sweeps.missable_note("S.S. Anne", p, lambda f: False)
    assert "16 trainers and 7 items still open" in note and "sails once you have HM01" in note and "your call" in note
    assert sweeps.missable_note("S.S. Anne", p, lambda f: f == 0x237) == ""                  # FLAG_GOT_HM01: the ship is gone anyway
    assert sweeps.missable_note("S.S. Anne", sweeps.progress("S.S. Anne", lambda f: f != 0x237), lambda f: False) == ""     # nothing left to lose
    assert sweeps.missable_note("Routes 24-25", sweeps.progress("Routes 24-25", lambda f: False), lambda f: False) == ""    # only areas that really close warn


def test_trainers_that_vanish_at_a_story_event_are_warned_about_until_it_happens_or_they_are_beaten():
    """Decomp: ViridianCity_Gym's DefeatedGiovanni sets FLAG_HIDE_MISC_KANTO_ROCKETS (Rocket Hideout x11, Mt. Moon B2F x4); the Five Island warehouse's DefeatedAdmin2 sets FLAG_HIDE_FIVE_ISLAND_ROCKETS."""
    flags = AREAS["Rocket Hideout"]["vanish"]
    assert [(n, name) for n, name, _t in flags] == [(173, "FLAG_HIDE_MISC_KANTO_ROCKETS")] and len(flags[0][2]) == 11
    assert len(AREAS["Mt. Moon"]["vanish"][0][2]) == 4 and len(AREAS["Five Island region"]["vanish"][0][2]) == 8
    note = sweeps.missable_note("Rocket Hideout", sweeps.progress("Rocket Hideout", lambda f: False), lambda f: False)
    assert "11 of its 11 trainers vanish when you beat Giovanni in the Viridian Gym" in note and "your call" in note
    beaten = set(flags[0][2][:6])
    assert "5 of its 11" in sweeps.missable_note("Rocket Hideout", sweeps.progress("Rocket Hideout", lambda f: f in beaten), lambda f: f in beaten)
    assert sweeps.missable_note("Rocket Hideout", sweeps.progress("Rocket Hideout", lambda f: f == 173), lambda f: f == 173) == ""      # the event already happened
    assert sweeps.missable_note("Rocket Hideout", sweeps.progress("Rocket Hideout", lambda f: True), lambda f: f != 173) == ""        # everyone is beaten
    assert "Rocket Admin" in sweeps.missable_note("Five Island region", sweeps.progress("Five Island region", lambda f: False), lambda f: False)


# ── the generator's helpers (synthetic input) ────────────────────────────────────────────────────

def test_the_generator_resolves_defines_and_trainer_scripts(tmp_path):
    from tools import gen_area_sweeps as g
    h = tmp_path / "flags.h"
    h.write_text("#define BASE 1000 // 0x3E8\n#define A (BASE +   2)\n#define B 0x4FF\n#define C (B + 1)\n#define D (A + 3)\n#define LOOP (LOOP + 1)\n")
    d = g.parse_defines(str(h))
    assert d["A"] == 1002 and d["C"] == 0x500 and d["D"] == 1005 and "LOOP" not in d
    scripts = tmp_path / "data" / "maps" / "X"
    scripts.mkdir(parents=True)
    (scripts / "scripts.inc").write_text("X_EventScript_Bob::\n\ttrainerbattle_single TRAINER_BOB, Intro, Defeat\n\tend\n\nX_EventScript_Sign::\n\tmsgbox Hi\n\tend\n")
    (tmp_path / "data" / "scripts").mkdir()
    (tmp_path / "data" / "scripts" / "trainers.inc").write_text("Route1_EventScript_Al::\n\ttrainerbattle_double TRAINER_AL, A, B, C\n\tend\n")
    idx = g.trainer_index(str(tmp_path))
    assert idx == {"X_EventScript_Bob": "TRAINER_BOB", "Route1_EventScript_Al": "TRAINER_AL"}


# ── observation + quest() ────────────────────────────────────────────────────────────────────────

pytest.importorskip("openai")
import agent.observation as obs  # noqa: E402


def _tick(here, flags, sig=None):
    return SimpleNamespace(run=SimpleNamespace(sweep_sig=sig), reader=SimpleNamespace(read_flag=lambda f: f in flags), here=here, overworld=True)


def test_the_sweep_line_appears_on_change_and_not_every_tick():
    moon = AREAS["Mt. Moon"]["maps"][0]
    flags = set()
    t = _tick(moon, flags)
    first = obs._sweep_line(t)
    assert len(first) == 1 and first[0].startswith("AREA PROGRESS: Mt. Moon: 0/11 trainers, 0/10 items")
    assert obs._sweep_line(t) == []                                                       # same counts: silent
    flags.add(AREAS["Mt. Moon"]["trainers"][0])                                           # a trainer beaten
    assert "1/11 trainers" in obs._sweep_line(t)[0]
    t.here = (0, 0)
    assert obs._sweep_line(t) == [] and t.run.sweep_sig is None                           # an unnamed map: silent, and the next entry shows the area again
    t.here = moon
    assert len(obs._sweep_line(t)) == 1


def test_the_sweep_line_warns_on_the_s_s_anne_and_celebrates_a_finished_area():
    ship = AREAS["S.S. Anne"]["maps"][0]
    line = obs._sweep_line(_tick(ship, set()))[0]
    assert line.startswith("AREA PROGRESS: S.S. Anne") and "⚠ S.S. Anne" in line and "your call" in line
    everything = {f for k in ("trainers", "items", "hidden") for f in AREAS["Viridian Forest"][k]}
    assert obs._sweep_line(_tick(AREAS["Viridian Forest"]["maps"][0], everything))[0].startswith("AREA COMPLETE: Viridian Forest")


def test_the_quest_listing_ends_with_the_started_areas_and_the_ship_warning():
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    flags = set(AREAS["Cerulean Gym"]["trainers"][:1])
    c.reader = SimpleNamespace(read_flag=lambda f: f in flags)
    out = c._sweep_listing()
    assert "AREA SWEEPS started, not finished" in out and "Cerulean Gym: 1/2 trainers" in out and "⚠ S.S. Anne" in out
    c.reader = SimpleNamespace(read_flag=lambda f: 1 / 0)
    assert c._sweep_listing() == ""                                                       # a read failure never breaks quest()
    assert re.search(r"^\s+Cerulean", out, re.M)
