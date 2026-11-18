"""Nav driver review (#216): travel rules as data, structured stop reasons, the depth guard, tolerated-failure logging,
the walk_to bounds check and battle-safe warp probing (no emulator)."""
import logging
from types import SimpleNamespace as NS

import pytest

from game.state import GameContext
from knowledge.travel_rules import NO_WALK, PC_TOWNS, no_walk_reason

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402


# ── data ───────────────────────────────────────────────────────────────────────────────────────
def test_cerulean_cannot_walk_back_west_but_everything_else_is_left_to_the_router():
    assert "ledges only go one way" in no_walk_reason((3, 3), (3, 2))          # Cerulean → Pewter
    assert no_walk_reason((3, 22), (1, 1))                                      # Route 4 → Mt. Moon 1F
    assert no_walk_reason((3, 3), (3, 24)) is None                              # Cerulean → Route 24 is fine
    assert no_walk_reason((3, 2), (3, 3)) is None                               # Pewter → Cerulean is fine
    assert len(NO_WALK) >= 1 and (3, 3) in PC_TOWNS and (3, 0) not in PC_TOWNS  # Pallet has no Center


# ── client fixture ──────────────────────────────────────────────────────────────────────────────────
def client(party=None, here=(3, 3), ctx=GameContext.OVERWORLD, badges=(2, 0b100)):
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_current_map=lambda: here, detect_context=lambda: ctx, read_party=lambda: party or [],
                  read_player_pos=lambda: (5, 5), read_badges=lambda: badges)
    c.ltm = NS(data={"gyms_beaten": []})
    return c


def mon(name, moves=(), sid=16):
    return NS(species_id=sid, species_name=name, nickname="", move_names=list(moves), max_hp=20, current_hp=20, level=10)


def test_the_no_walk_message_says_what_to_do_instead_by_what_the_party_can_do():
    c = client([mon("Pidgeotto", ["Fly", "Gust"], 17)])
    out = c._go_to("Pewter City")
    assert out.startswith("There is no walking route to Pewter City") and "knows Fly: fly_to" in out
    assert c._stop_reason == "no_walk" and c.last_trip_stop["reason"] == "no_walk"
    no_badge = client([mon("Pidgeotto", ["Fly"], 17)], badges=(0, 0))
    assert "Thunder Badge" in no_badge._go_to("Pewter City")
    capable = client([mon("Pidgey", ["Gust"], 16)])
    assert "could learn it" in capable._go_to("Pewter City")
    nobody = client([mon("Rattata", ["Tackle"], 19)])
    assert "catch a Fly-capable bird" in nobody._go_to("Pewter City")


# ── stop reasons ──────────────────────────────────────────────────────────────────────────────────────
def test_battle_stop_reasons_are_classified_from_the_real_messages():
    r = AgentClient._battle_stop_reason
    assert r("A wild RATTATA L4 (HP 14/14) appeared at Route 1 on the way to Viridian City.") == "battle"
    assert r("A TRAINER battle started at Route 3 on the way to Pewter City (you can't flee it).") == "battle"
    assert r("Lost a trainer battle en route to Pewter City — heal …") == "lost"
    assert r("Lost to a trainer near Route 4 2 times — you're not strong enough …") == "lost"
    assert r("Beat a trainer en route to X, but your lead's HP is low (20%) — call heal()") == "low_hp"
    assert r("Fled a wild battle en route to X, but your lead's HP is low (10%) — call heal()") == "low_hp"
    assert r("A tough trainer battle en route to X isn't resolving on autopilot — take over") == "battle_unresolved"
    assert r("A wild battle started en route to X and the escape failed — fight it") == "battle_unresolved"


def test_the_outermost_trip_records_the_reason_and_emits_one_event():
    from agent import events
    events.reset()
    c = client()
    c._go_to_inner = lambda *a, **k: c._stop("budget", "Stopped at Route 2 en route to Pewter City after the 40-hop budget")
    out = c._go_to("Pewter City")
    assert "40-hop budget" in out and c.last_trip_stop == {"reason": "budget", "target": "Pewter City", "map": (3, 3)}
    assert [e["text"] for e in events.recent("trip")] == ["trip to Pewter City ended: budget"]
    c._go_to_inner = lambda *a, **k: c._stop("arrived", "Arrived at Pewter City.")
    c._go_to("Pewter City")
    assert len(events.recent("trip")) == 1                                    # an arrival is not a "ended" event
    events.reset()


def test_nested_travel_is_cut_off_at_the_depth_limit():
    c = client()
    depth_seen = []

    def inner(dest, mode, auto, resume):
        depth_seen.append(c._go_depth)
        return c._go_to(dest, mode, auto, resume)                              # a heal/first-visit loop back into travel
    c._go_to_inner = inner
    out = c._go_to("Pokemon Center")
    assert depth_seen == [1, 2, 3, 4] and "nested 4 deep" in out
    assert c._stop_reason == "nested" and c._go_depth == 0                    # the counter always unwinds


from agent.skills import base as base_mod  # noqa: E402


# ── tolerated failures are logged once, not hidden ───────────────────────────────────────────────────
def test_gate_read_failures_still_let_travel_go_but_are_logged_once(caplog):
    base_mod._LOGGED.clear()
    c = client()
    c._party_knows = lambda mid: 1 / 0
    req = NS(alt_flag=None, kind="hm", value="Cut")
    with caplog.at_level(logging.WARNING, logger=base_mod.logger.name):
        assert c._gate_ok(req) is True and c._gate_ok(req) is True
    msgs = [r.getMessage() for r in caplog.records if "requirement" in r.getMessage()]
    assert len(msgs) == 1 and "hm" in msgs[0]


def test_advance_to_control_logs_a_failing_forced_switch_once(caplog):
    base_mod._LOGGED.clear()
    c = client(ctx=GameContext.IN_MENU)
    c._send_next_mon = lambda: 1 / 0
    c.mgba = NS(read32=lambda a: 0, tap=lambda b: None, tick=lambda n=1: None)
    with caplog.at_level(logging.WARNING, logger=base_mod.logger.name):
        c._advance_to_control(tries=3)
    assert sum("_send_next_mon failed" in r.getMessage() for r in caplog.records) == 1


# ── walk_to bounds and warp probing ────────────────────────────────────────────────────────────────────
def test_walk_to_rejects_tiles_outside_the_map_with_the_real_size():
    c = client()
    c.tilemap = NS(_width=20, _height=15, refresh=lambda: True)
    seen = []
    c._walk_to = lambda x, y: seen.append((x, y)) or "ok"
    assert "outside this map" in c._walk_to_tool(-1, 5) and "x 0-19, y 0-14" in c._walk_to_tool(3, 15)
    assert c._walk_to_tool(19, 14) == "ok" and seen == [(19, 14)]
    c.tilemap = NS(_width=None, _height=None, refresh=lambda: True)             # map size unknown: don't block
    assert c._walk_to_tool(99, 99) == "ok"


def test_probing_a_warp_stops_when_a_battle_starts():
    c = client()
    c.mgba = NS(hold=lambda *a: None, tick=lambda n=1: None)
    c._walk_to = lambda x, y: None
    state = {"battle": True}
    c.reader.detect_context = lambda: GameContext.IN_BATTLE if state["battle"] else GameContext.OVERWORLD
    walks = []
    c._walk_to = lambda x, y: walks.append((x, y))
    assert c._probe_warp((7, 4)) is False and len(walks) == 1               # gave up after the first approach


def test_route_4_mt_moon_pocket_walks_straight_back_to_route_3():
    """Regression: healing at Route 4's Pokémon Center drops you in the west pocket, one step from Route 3 — NO_WALK (meant for the
    Cerulean-side ledges) said Route 3 / Route 2 / Viridian Forest were unreachable, so grind went all the way round to Route 22."""
    assert no_walk_reason((3, 22), (3, 21), (12, 5)) is None                    # the pocket: region 2
    assert no_walk_reason((3, 22), (1, 1), (12, 6)) is None
    assert no_walk_reason((3, 22), (3, 21), (40, 6))                            # the Cerulean-side ledge pocket still can't climb back
    assert no_walk_reason((3, 22), (3, 21))                                     # position unknown: keep the old, cautious answer


def test_grass_skip_reasons_name_the_route_and_do_not_pile_up():
    c = client()
    c._gate_why = ""
    for why in ("Route 24: a", "Route 24: a", "Route 25: b", "Route 9: c", "Route 5: d"):
        c._add_gate_why(why)
    assert c._gate_why == "Route 24: a | Route 25: b | Route 9: c"
    assert "Route 25: b" in c._why_no_grass() and c._gate_why == ""


def test_walk_to_checks_the_size_of_the_map_you_are_on_not_the_one_you_just_left():
    """Regression (two watched runs): walk_to right after a tool that changed maps was checked against the OLD map's size —
    (10,10) 'outside' a 15x10 Center while standing in Vermilion, (11,35) 'outside' Route 4's 108x20 while in Mt. Moon 1F."""
    c = client()
    c.tilemap = NS(_width=15, _height=10)
    c.tilemap.refresh = lambda: (setattr(c.tilemap, "_width", 108), setattr(c.tilemap, "_height", 40), True)[-1]
    c._walk_to = lambda x, y: "ok"
    assert c._walk_to_tool(11, 35) == "ok"
