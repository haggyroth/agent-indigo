"""The side-quest log (#356): availability, the grouped listing, the one-line digest, League advice — information, never a wall."""
from types import SimpleNamespace

import pytest

from knowledge import story_beats as sb
from knowledge.aides import AIDES
from test_story_beats import checker

PARCEL = ["delivered_oaks_parcel"]


def _status(badges=(), flags=(), items=()):
    return sb.evaluate(checker(badges=badges, flags=flags, items=items, milestones=PARCEL))


def test_every_optional_beat_has_a_payoff_and_the_tiers_are_right():
    optional = {b.key for b in sb.BEATS if b.optional}
    assert optional == set(sb.SIDE_INFO)                                  # a new optional beat must say what it is worth
    for b in sb.BEATS:
        assert (b.tier == "side") == b.optional and (b.payoff != "") == b.optional, b.key
    assert all(b.tier == "main" for b in sb.BEATS if not b.optional)


def test_the_gates_match_the_oak_aide_counts_in_the_decomp_data():
    gates = {b.key: dict(b.gate).get("owned") for b in sb.BEATS if b.gate}
    assert gates == {key: need for key, need, _flag, _label in AIDES}


def test_availability_follows_the_story_and_the_gates():
    st = _status(badges=[0, 1], flags=[0x234, 0x237])                    # Brock + Misty, the SS Ticket and Cut
    now = {b.key for b in sb.side_quests(st, sb.SideCtx(badges=2, owned=5))["now"]}
    assert {"dig", "old_rod", "bike", "running_shoes", "magikarp"} <= now
    assert "flash" not in now and "good_rod" not in now                    # Flash needs 10 caught AND the Thunder Badge; Good Rod needs the Snorlax road
    locked = dict((b.key, why) for b, why in sb.side_quests(st, sb.SideCtx(badges=2, owned=5))["locked"])
    assert "first: surge" in locked["flash"] or "needs 10 species" in locked["flash"]
    st = _status(badges=[0, 1, 2], flags=[0x234, 0x237])                  # + the Thunder Badge
    assert "flash" in {b.key for b in sb.side_quests(st, sb.SideCtx(badges=3, owned=9))["locked"] and [x for x, _ in sb.side_quests(st, sb.SideCtx(badges=3, owned=9))["locked"]]}
    assert dict((b.key, why) for b, why in sb.side_quests(st, sb.SideCtx(badges=3, owned=9))["locked"])["flash"] == "needs 10 species caught (you have 9)"
    assert "flash" in {b.key for b in sb.side_quests(st, sb.SideCtx(badges=3, owned=10))["now"]}


def test_a_finished_side_quest_leaves_the_open_list():
    st = _status(badges=[0, 1], flags=[0x234, 0x237, 0x240])               # + FLAG_GOT_OLD_ROD
    sq = sb.side_quests(st, sb.SideCtx(badges=2))
    assert "old_rod" in [b.key for b in sq["done"]] and "old_rod" not in [b.key for b in sq["now"]]


def test_digest_is_one_line_with_payoffs_and_silent_when_nothing_is_open():
    st = _status(badges=[0, 1], flags=[0x234, 0x237])
    line = sb.digest(st, sb.SideCtx(badges=2, owned=3))
    assert line.startswith("SIDE QUESTS you can do now") and "dig (TM28 Dig)" in line and "\n" not in line and "your call" in line
    assert "more unlock as the story advances" in line
    assert sb.digest(sb.evaluate(lambda spec: True), sb.SideCtx(badges=8, owned=151, game_clear=True)) == ""     # everything done: silent
    assert sb.digest(_status(), sb.SideCtx()) == ""                                                               # nothing open yet: silent


def test_the_listing_groups_main_side_now_and_side_locked_and_keeps_the_marks():
    st = _status(badges=[0, 1, 2, 3], flags=[0x234, 0x237, 0x240], items=[sb.SS_TICKET])
    text = sb.listing(st, sb.SideCtx(badges=4, owned=12))
    assert text.index("MAIN") < text.index("SIDE QUESTS — available now") < text.index("SIDE QUESTS — not yet")
    assert "✔ erika" in text and "▶ rocket_hideout" in text and "[quest('rocket_hideout') runs it]" in text and "… pokemon_tower" in text
    assert "▶ dig:" in text and "TM28 Dig" in text and "yours to choose" in text
    assert "SIDE QUESTS — done: old_rod" in text
    assert "… itemfinder" in text and "needs 30 species caught (you have 12)" in text
    main_part = text.split("SIDE QUESTS")[0]
    import re
    assert not re.search(r"^[✔▶…] (old_rod|dig|bike|itemfinder):", main_part, re.M)                              # side quests are not in the main chain
    assert "POST-GAME" not in text                                                                                # nothing post-game yet


def test_league_advice_counts_what_is_open_and_never_blocks():
    st = _status(badges=range(8), flags=[0x234, 0x237])
    advice = sb.league_advice(st, sb.SideCtx(badges=8, owned=20))
    assert advice.startswith(str(len(sb.side_quests(st, sb.SideCtx(badges=8, owned=20))["now"]))) and "optional, your call" in advice
    assert sb.league_advice(sb.evaluate(lambda spec: True), sb.SideCtx(badges=8, owned=151)) == ""


# ── glue: the observation line is throttled, quest() and League prep carry the log ───────────────────────────────

pytest.importorskip("openai")
import agent.observation as obs  # noqa: E402


def _tick(status, ctx, run):
    return SimpleNamespace(run=run, reader=SimpleNamespace(), state=SimpleNamespace(party=[]), ltm=SimpleNamespace(data={}))


def test_the_side_quest_line_appears_when_the_set_changes_and_not_every_tick(monkeypatch):
    import agent.story as story
    state = {"flags": [0x234, 0x237]}
    monkeypatch.setattr(obs, "_story_status_for", lambda t: _status(badges=[0, 1], flags=state["flags"]))
    monkeypatch.setattr(story, "side_ctx", lambda reader: sb.SideCtx(badges=2, owned=3))
    run = SimpleNamespace(sidequest_sig=None)
    t = _tick(None, None, run)
    first = obs._side_quest_line(t)
    assert len(first) == 1 and first[0].startswith("SIDE QUESTS")
    assert obs._side_quest_line(t) == [] and obs._side_quest_line(t) == []                 # same set: silent
    state["flags"] = [0x234, 0x237, 0x240]                                                # Old Rod collected: the set changed
    again = obs._side_quest_line(t)
    assert len(again) == 1 and "old_rod" not in again[0]


def test_quest_listing_and_league_prep_use_the_log(monkeypatch):
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_badges=lambda: (2, 3), read_pokedex=lambda: (4, 6), read_flag=lambda n: False)
    monkeypatch.setattr(c, "_story", lambda: _status(badges=[0, 1], flags=[0x234, 0x237]), raising=False)
    out = c._quest_tool("")
    assert "SIDE QUESTS — available now" in out and "dig" in out
