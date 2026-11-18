"""The story chain (knowledge.story_beats): integrity, ordering, state evaluation, the one-line observation hint, the plans (no emulator)."""
from knowledge import story_beats as sb


def checker(flags=(), items=(), badges=(), milestones=()):
    flags, items, badges, milestones = set(flags), set(items), set(badges), set(milestones)

    def check(spec):
        kind, v = spec
        return {"flag": v in flags, "item": v in items, "badge": v in badges, "milestone": v in milestones}[kind]
    return check


def test_the_chain_is_consistent_and_topologically_ordered():
    keys = [b.key for b in sb.BEATS]
    assert len(keys) == len(set(keys))
    for i, b in enumerate(sb.BEATS):
        assert b.title and b.where and b.steps and b.done, b.key
        for n in b.needs:
            assert n in keys[:i], f"{b.key} needs {n}, which must come EARLIER in the chain"
        for kind, _v in b.done:
            assert kind in ("flag", "item", "badge", "milestone")


def test_every_story_beat_before_the_elite_four_the_goal_names_is_present():
    for k in ("rocket_hideout", "silph_co", "pokemon_tower", "tea", "poke_flute", "pokemon_mansion", "snorlax", "sabrina", "koga", "blaine",
              "giovanni", "victory_road", "surf", "strength", "cut", "ss_ticket"):
        assert k in sb.BY_KEY, k
    assert sb.resolve("tower") is sb.BY_KEY["pokemon_tower"] and sb.resolve("flute") is sb.BY_KEY["poke_flute"]
    assert sb.resolve("Silph Co.") is sb.BY_KEY["silph_co"] and sb.resolve("mansion") is sb.BY_KEY["pokemon_mansion"]
    assert sb.resolve("nonsense-xyz") is None


def test_badge_bits_match_the_game_order():
    bits = {b.key: next(v for k, v in b.done if k == "badge") for b in sb.BEATS if any(k == "badge" for k, _ in b.done)}
    assert bits == {"brock": 0, "misty": 1, "surge": 2, "erika": 3, "koga": 4, "sabrina": 5, "blaine": 6, "giovanni": 7}


def test_evaluate_marks_done_next_and_blocked():
    # a fresh run after Erika, no Silph Scope: Rocket Hideout and the Tea are open, the Tower is not
    st = sb.evaluate(checker(milestones=["delivered_oaks_parcel"], badges=[0, 1, 2, 3], flags=[0x234, 0x237], items=[sb.SS_TICKET]))
    assert st["erika"] == "done" and st["rocket_hideout"] == "next" and st["tea"] == "next"
    assert st["pokemon_tower"] == "blocked" and st["silph_co"] == "blocked" and st["giovanni"] == "blocked"
    nxt = [b.key for b in sb.next_beats(st)]
    assert nxt[0] == "rocket_hideout" and "tea" in nxt and "fly" not in nxt            # optional beats are left out by default
    assert "fly" in [b.key for b in sb.next_beats(st, include_optional=True)]


def test_the_chain_unlocks_in_story_order():
    f, i = {0x234, 0x237}, {sb.SS_TICKET}
    st = sb.evaluate(checker(milestones=["delivered_oaks_parcel"], badges=[0, 1, 2, 3], flags=f, items=i | {sb.SILPH_SCOPE}))
    assert st["pokemon_tower"] == "next"
    st = sb.evaluate(checker(milestones=["delivered_oaks_parcel"], badges=[0, 1, 2, 3], flags=f | {0x23C}, items=i | {sb.SILPH_SCOPE}))
    assert st["poke_flute"] == "next"
    st = sb.evaluate(checker(milestones=["delivered_oaks_parcel"], badges=[0, 1, 2, 3], flags=f | {0x23C, 0x23D, 0x253}, items=i | {sb.SILPH_SCOPE}))
    assert st["snorlax"] == "done" and st["koga"] == "next"
    st = sb.evaluate(checker(milestones=["delivered_oaks_parcel"], badges=[0, 1, 2, 3, 4], flags=f | {0x23C, 0x23D, 0x253, 0x2A6, 0x250},
                             items=i | {sb.SILPH_SCOPE}))
    assert st["sabrina"] == "next" and st["surf"] == "next"
    assert st["pokemon_mansion"] == "blocked" and st["giovanni"] == "blocked"
    st = sb.evaluate(checker(milestones=["delivered_oaks_parcel"], badges=range(8), flags=f | {0x23C, 0x23D, 0x253, 0x2A6, 0x250, 0x899},
                             items=i | {sb.SILPH_SCOPE, sb.SECRET_KEY}))
    assert st["victory_road"] == "done" or st["victory_road"] == "next"


def test_tea_is_done_by_the_flag_even_though_the_guard_takes_the_item():
    assert sb.evaluate(checker(badges=[0, 1, 2, 3], flags=[0x2A6]))["tea"] == "done"       # FLAG_GOT_TEA stays set after the guard drinks it


def test_story_line_names_the_next_required_beat_and_how_to_run_it():
    st = sb.evaluate(checker(milestones=["delivered_oaks_parcel"], badges=[0, 1, 2, 3], flags=[0x234, 0x237], items=[sb.SS_TICKET]))
    line = sb.story_line(st)
    assert line.startswith("STORY NEXT: Silph Scope") and "quest('rocket_hideout')" in line and "also open: tea" in line
    st = sb.evaluate(checker(milestones=["delivered_oaks_parcel"], badges=[0, 1, 2, 3], flags=[0x234, 0x237, 0x2A6], items=[sb.SS_TICKET, sb.SILPH_SCOPE]))
    assert "Pokémon Tower" in sb.story_line(st) and "quest('pokemon_tower')" in sb.story_line(st)               # a scripted beat: just run it
    done = sb.evaluate(lambda spec: True)
    assert sb.story_line(done) == ""


def test_plan_is_state_aware():
    st = sb.evaluate(checker(badges=[0, 1, 2, 3], flags=[0x234, 0x237], items=[sb.SS_TICKET], milestones=["delivered_oaks_parcel"]))
    tower = sb.plan(sb.BY_KEY["pokemon_tower"], st)
    assert "Not yet" in tower and "Silph Scope" in tower and "quest('rocket_hideout')" in tower and "Mr. Fuji" in tower
    assert "runs it" in sb.plan(sb.BY_KEY["tea"], st) and "Celadon Mansion" in sb.plan(sb.BY_KEY["tea"], st)
    assert "Already done" in sb.plan(sb.BY_KEY["erika"], st)


def test_listing_marks_each_beat_and_scripted_ones():
    st = sb.evaluate(checker(badges=[0, 1, 2, 3], flags=[0x234, 0x237], items=[sb.SS_TICKET], milestones=["delivered_oaks_parcel"]))
    text = sb.listing(st)
    assert "✔ erika" in text and "▶ rocket_hideout" in text and "[quest('rocket_hideout') runs it]" in text
    assert "… pokemon_tower" in text and "first: rocket_hideout" in text and "[guide]" in text


# ── the quest tool and the observation line, against a fake game (no emulator) ─────────────────────────────────────
from types import SimpleNamespace   # noqa: E402

import pytest   # noqa: E402

pytest.importorskip("openai")


class FakeReader:
    def __init__(self, flags=(), items=(), badges_mask=0, map_key=(3, 6), moves=()):
        self.flags, self.items, self.mask, self.map, self.moves = set(flags), list(items), badges_mask, map_key, list(moves)

    def read_flag(self, n): return n in self.flags
    def read_key_items(self): return list(self.items)
    def read_badges(self): return bin(self.mask).count("1"), self.mask
    def read_current_map(self): return self.map
    def read_party(self): return [SimpleNamespace(move_ids=self.moves, species_name="X", level=30)]
    def detect_context(self): return SimpleNamespace(name="OVERWORLD")


def client(reader, milestones=("delivered_oaks_parcel",)):
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = reader
    c.ltm = SimpleNamespace(data={"milestones": list(milestones)})
    return c


AFTER_ERIKA = dict(flags={0x234, 0x237}, items=[sb.SS_TICKET], badges_mask=0b1111, moves=[15])         # ticket, HM01 taught, 4 badges


def test_quest_lists_the_chain_with_the_next_beats_marked():
    out = client(FakeReader(**AFTER_ERIKA))._quest_tool()
    assert "✔ erika" in out and "▶ rocket_hideout" in out and "▶ tea" in out and "… pokemon_tower" in out


def test_a_guide_only_beat_prints_a_state_aware_plan_not_an_error():
    out = client(FakeReader(**AFTER_ERIKA))._quest_tool("sabrina")
    assert out.startswith("No script for this one yet") and "Not yet" in out and "quest('silph_co')" in out and "teleport-pad" in out
    after_silph = dict(AFTER_ERIKA, flags={0x234, 0x237, 0x2A6, 0x250})
    out = client(FakeReader(**after_silph))._quest_tool("sabrina")
    assert "Not yet" not in out and "Alakazam" in out


def test_a_scripted_beat_runs_its_script_and_says_what_it_needs_first():
    out = client(FakeReader(**AFTER_ERIKA))._quest_tool("pokemon_tower")
    assert "Silph Scope" in out and "quest('rocket_hideout')" in out                       # needs the scope: the script refuses with the fix


def test_a_finished_beat_says_so_and_an_unknown_name_lists_the_chain():
    c = client(FakeReader(**AFTER_ERIKA))
    assert "already done" in c._quest_tool("erika")
    assert "No quest called 'zzz'" in c._quest_tool("zzz") and "Story, start to Elite Four" in c._quest_tool("zzz")


def test_cut_is_done_only_once_it_is_taught_not_when_hm01_is_in_the_bag():
    untaught = dict(AFTER_ERIKA, moves=[])
    assert client(FakeReader(**untaught))._driver_done()["cut"] is False
    assert client(FakeReader(**AFTER_ERIKA))._driver_done()["cut"] is True


def test_rocket_hideout_is_not_done_while_still_inside_it():
    inside = FakeReader(items=[sb.SILPH_SCOPE], map_key=(1, 45), **{k: v for k, v in AFTER_ERIKA.items() if k != "items"})
    assert client(inside)._driver_done()["rocket_hideout"] is False                      # quest('rocket_hideout') walks you out
    outside = FakeReader(items=[sb.SILPH_SCOPE], map_key=(3, 6), **{k: v for k, v in AFTER_ERIKA.items() if k != "items"})
    assert client(outside)._driver_done()["rocket_hideout"] is True


def test_the_observation_story_line_follows_the_game():
    from agent.observation import _story_status_for
    t = SimpleNamespace(reader=FakeReader(**AFTER_ERIKA), state=SimpleNamespace(party=[SimpleNamespace(move_ids=[15])]),
                        ltm=SimpleNamespace(data={"milestones": ["delivered_oaks_parcel"]}))
    line = sb.story_line(_story_status_for(t))
    assert line.startswith("STORY NEXT: Silph Scope") and "quest('rocket_hideout')" in line
