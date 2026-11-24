"""The rest of #270 / #271 (no emulator): money targets per beat and how to earn the gap, healing-supply checks, the listing's level tags."""
from types import SimpleNamespace as NS

import pytest

from knowledge import story_beats as sb
from knowledge.beat_readiness import NEEDS, readiness, recommendation, supplies_short
from knowledge.money import MONEY_NEEDS, earn_advice, money_line, treasure_value


def team(*levels):
    return [NS(level=lv, move_ids=[]) for lv in levels]


def test_a_strong_team_with_an_empty_bag_is_still_not_ready_for_victory_road():
    out = readiness("victory_road", team(44, 40, 38, 36, 30), {13: 2})
    assert "Not ready" in out and "0.4 Potions / Restores in the bag (10 recommended" in out and "0 Revives (3 recommended)" in out      # 2 Potions (20 HP each) are 0.4 of a full heal at L44
    assert "best Pokémon" not in out                                       # the levels are fine: only the supplies are named
    assert readiness("victory_road", team(44, 40, 38, 36, 30), {21: 10, 24: 3}) == ""             # Hyper Potions count in full; Revives too
    assert readiness("victory_road", team(44, 40, 38, 36, 30), {13: 6, 22: 4, 24: 3}) != ""       # …but 10 weak potions are not 10 heals at this level


def test_without_a_bag_only_levels_are_checked_and_both_shortfalls_are_reported_together():
    assert readiness("victory_road", team(44, 40, 38, 36, 30)) == ""
    out = readiness("elite_four", team(40, 30), {})
    assert "best Pokémon is L40" in out and "Revives" in out and "; and " in out
    assert supplies_short("tea", {}) == [] and supplies_short("elite_four", None) == []


def test_the_plan_mentions_the_supplies_and_the_listing_tags_the_recommended_level():
    assert "carry 12+ Potions and 4+ Revives" in recommendation("elite_four")
    listing = sb.listing({"victory_road": "next", "parcel": "done"})
    assert "victory_road: " in listing and "[rec. L42+]" in listing
    assert "parcel" in listing and "[rec." not in next(ln for ln in listing.splitlines() if "parcel" in ln)


def test_every_money_need_belongs_to_a_beat_with_a_readiness_entry():
    assert set(MONEY_NEEDS) == set(NEEDS)
    assert MONEY_NEEDS["elite_four"][0] > MONEY_NEEDS["victory_road"][0] > MONEY_NEEDS["rocket_hideout"][0]


def test_money_line_names_the_gap_and_sells_treasure_before_suggesting_fights():
    out = money_line("elite_four", 4000, {110: 2, 109: 1}, team(60))
    assert "short by ¥16000" in out and "shop(sell=true) sells your treasure for about ¥14900" in out and "TRAINER battles" in out
    assert money_line("elite_four", 4000, {110: 4}, team(60)).count("TRAINER") == 0        # ¥20000 of Nuggets covers it
    assert money_line("elite_four", 25000, {}, team(60)) == "" and money_line("tea", 0, {}, team(60)) == ""


def test_pay_day_is_mentioned_when_a_party_member_knows_it():
    assert "Pay Day" in earn_advice({}, [NS(move_ids=[6, 1, 0, 0])], 1000)
    assert "Pay Day" not in earn_advice({}, [NS(move_ids=[33])], 1000)
    assert treasure_value({110: 1, 106: 2, 13: 5}) == 5000 + 1400


def test_the_quest_gate_warns_about_supplies_once_then_goes_ahead():
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_party=lambda: team(40, 30, 30), read_bag=lambda: {}, read_items_pocket=lambda: [])
    c._story = lambda: {b.key: "next" for b in sb.BEATS}
    ran = []
    c._get_silph_scope = lambda auto: (ran.append(1), "driver ran")[1]
    out = c._quest_tool("rocket_hideout")
    assert out.startswith("Not ready for quest('rocket_hideout')") and "Potions" in out and not ran
    c.reader = NS(read_party=lambda: team(40, 30, 30), read_bag=lambda: {13: 9, 24: 2}, read_items_pocket=lambda: [(13, 9), (24, 2)])
    c._ready_warned.discard("rocket_hideout")
    assert c._quest_tool("rocket_hideout") == "driver ran"


def test_league_supplies_are_bought_revives_first_then_max_potions_within_the_money():
    from knowledge.money import MAX_POTION, REVIVE, supply_purchases
    assert supply_purchases("elite_four", 21500, {}) == [(REVIVE, 4), (MAX_POTION, 6)]
    assert supply_purchases("elite_four", 3000, {}) == [(REVIVE, 2)]                     # not enough for a Max Potion after the first Revives
    assert supply_purchases("elite_four", 99999, {24: 4, 19: 12}) == []                  # already stocked
    assert supply_purchases("elite_four", 99999, {21: 12, 24: 4}) == []                  # Hyper Potions count in full
    assert supply_purchases("elite_four", 99999, {13: 5, 24: 1}) == [(REVIVE, 3), (MAX_POTION, 12)]       # 5 Potions are not 5 heals for a L54 team (they are ~0.9)
    assert supply_purchases("tea", 99999, {}) == [] and supply_purchases("elite_four", 0, {}) == []


def test_effective_heals_count_by_strength_only_for_the_late_beats():
    from knowledge.beat_readiness import effective_heals
    assert effective_heals({13: 10}, 26) == 10                                           # early beats: every grade is one
    assert effective_heals({13: 10}, 54) == pytest.approx(10 * 20 / 135)
    assert effective_heals({21: 3, 20: 1, 19: 1, 22: 2}, 54) == pytest.approx(3 + 1 + 1 + 2 * 50 / 135)


def test_a_potion_is_never_replaced_by_a_revive_at_a_mart_that_lacks_potions():
    from agent.skills.overworld import OverworldMixin
    from knowledge.shop_stock import ITEM_LABELS
    for sub in OverworldMixin._SHOP_SUBSTITUTES[13]:
        assert "Potion" in ITEM_LABELS[sub], ITEM_LABELS[sub]
