"""record_milestone is checked against the game where the game can say (#379)."""
import types

import pytest

from knowledge import story_beats
from knowledge.milestone_evidence import EVIDENCE, is_verifiable, verify
from knowledge.leafgreen_data import MILESTONES


def test_evidence_agrees_with_the_flags_the_story_beats_trust():
    beats = {b.key: b.done for b in story_beats.BEATS}
    pairs = {"got_cut": "cut", "got_flash": "flash", "got_fly": "fly", "got_surf": "surf", "got_strength": "strength", "rescued_mr_fuji": "pokemon_tower",
             "got_poke_flute": "poke_flute", "woke_snorlax_12": "snorlax", "got_silph_scope": "rocket_hideout", "delivered_oaks_parcel": "parcel"}
    for milestone, beat in pairs.items():
        assert set(EVIDENCE[milestone]) <= set(beats[beat]), (milestone, beat)


def test_every_evidence_key_is_a_real_recordable_milestone_and_gym_wins_are_checked_against_the_badge_byte():
    assert set(EVIDENCE) <= set(MILESTONES)
    assert EVIDENCE["beat_brock"] == (("badge", 0),) and EVIDENCE["beat_giovanni"] == (("badge", 7),)


def test_verify():
    assert verify("cleared_rock_tunnel", lambda s: False) == (True, "")             # no RAM signal: taken on the model's word
    ok, why = verify("got_surf", lambda s: False)
    assert not ok and "does not confirm" in why and "0x239" in why
    assert verify("got_surf", lambda s: s == ("flag", 0x239)) == (True, "")
    assert verify("got_poke_flute", lambda s: s[0] == "item")[0]                     # ANY spec is enough
    assert is_verifiable("got_cut") and not is_verifiable("woke_snorlax_16")


# ── the tool and the journal ─────────────────────────────────────────────────────────────────────

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402
from memory.long_term import LongTermMemory  # noqa: E402


def _client(tmp_path, flags=(), party=1):
    c = AgentClient.__new__(AgentClient)
    c.reader = types.SimpleNamespace(read_flag=lambda n: n in flags, read_key_items=lambda: [], read_badges=lambda: (0, 0),
                                     read_party=lambda: [object()] * party)
    c.ltm = LongTermMemory(path=tmp_path / "p.json")
    c._grind_run = None
    return c


def test_a_milestone_the_game_does_not_confirm_is_refused(tmp_path):
    c = _client(tmp_path)
    out = c._execute_inner("record_milestone", '{"name": "got_surf"}')
    assert out.startswith("Not recorded") and "got_surf" not in c.ltm.data["milestones"]


def test_a_confirmed_milestone_is_recorded_and_marked_model_asserted(tmp_path):
    c = _client(tmp_path, flags={0x239})
    assert "recorded" in c._execute_inner("record_milestone", '{"name": "got_surf"}')
    assert "got_surf" in c.ltm.data["milestones"] and c.ltm.data["model_milestones"] == ["got_surf"]
    assert "already recorded" in c._execute_inner("record_milestone", '{"name": "got_surf"}')


def test_a_milestone_with_no_ram_signal_is_taken_on_the_models_word_and_says_so(tmp_path):
    c = _client(tmp_path)
    out = c._execute_inner("record_milestone", '{"name": "cleared_rock_tunnel"}')
    assert "taken on your word" in out and "cleared_rock_tunnel" in c.ltm.data["milestones"]


def test_an_unknown_milestone_is_still_rejected_and_a_gym_win_needs_the_badge(tmp_path):
    c = _client(tmp_path)
    assert "Invalid milestone" in c._execute_inner("record_milestone", '{"name": "beat_the_game"}')
    assert c._execute_inner("record_milestone", '{"name": "beat_brock"}').startswith("Not recorded")      # no badge in the (fake) save


def test_startup_drops_hand_recorded_milestones_the_cartridge_contradicts(tmp_path):
    ltm = LongTermMemory(path=tmp_path / "p.json")
    ltm.add_milestone("got_cut", source="model")
    ltm.add_milestone("got_surf", source="model")
    ltm.add_milestone("cleared_rock_tunnel", source="model")
    ltm.add_milestone("got_fly")                                                     # derived by the game loop: never second-guessed here
    dropped = ltm.reconcile_model_milestones(lambda s: s == ("flag", 0x237))       # this save has HM01 only
    assert dropped == ["got_surf"]
    assert set(ltm.data["milestones"]) == {"got_cut", "cleared_rock_tunnel", "got_fly"}
    assert LongTermMemory(path=tmp_path / "p.json").data["model_milestones"] == ["got_cut", "cleared_rock_tunnel"]      # and it persists (#371)


def test_the_story_check_understands_a_party_spec():
    from agent.story import make_done_check
    r = types.SimpleNamespace(read_party=lambda: [1, 2])
    assert make_done_check(r, None)(("party", 2)) and not make_done_check(r, None)(("party", 3))
