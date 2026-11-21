"""The observation says how the player is travelling (no emulator)."""
from types import SimpleNamespace as NS

from agent.observation import _header
from game.state import GameContext


def tick(biking=False, surfing=False, road=False, ctx=GameContext.OVERWORLD):
    reader = NS(is_biking=lambda: biking, is_surfing=lambda: surfing, read_flag=lambda f: road and f == 0x830)
    return NS(state=NS(context=ctx, player_x=3, player_y=4), ltm=NS(data={"badges_earned": 5}), in_battle=False, reader=reader, run=NS(prev_state=None),
              overworld=ctx == GameContext.OVERWORLD)


def lines(**kw):
    return " | ".join(_header(tick(**kw)))


def test_riding_the_bicycle_is_reported():
    assert "riding the Bicycle" in lines(biking=True) and "use_item('Bicycle')" in lines(biking=True)


def test_the_cycling_road_says_you_cannot_get_off_and_it_runs_south():
    out = lines(biking=True, road=True)
    assert "Cycling Road keeps you on it" in out and "south" in out


def test_surfing_is_reported_and_plain_walking_adds_nothing():
    assert "surfing" in lines(surfing=True)
    assert "Travelling" not in lines()


def test_nothing_is_added_off_the_field():
    assert "Travelling" not in lines(biking=True, ctx=GameContext.TRANSITIONING)
