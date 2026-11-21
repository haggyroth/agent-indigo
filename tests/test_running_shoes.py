"""Hold B while walking once the Running Shoes are owned (no emulator): when running is allowed and when it is not."""
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402
from knowledge.map_dims import RUN_ALLOWED  # noqa: E402

VERMILION, POKEMON_CENTER, VICTORY_ROAD_1F, MANSION_1F = (3, 5), (9, 1), (1, 39), (1, 59)


def client(shoes=True, biking=False, surfing=False, has_run=True):
    c = AgentClient.__new__(AgentClient)
    c.mgba = NS(run_step=lambda b: None) if has_run else NS()
    c.reader = NS(read_flag=lambda f: shoes if f == 0x82F else False, is_biking=lambda: biking, is_surfing=lambda: surfing)
    c._in_puzzle = False
    return c


def test_the_map_header_data_marks_towns_routes_and_caves_runnable_and_buildings_not():
    assert VERMILION in RUN_ALLOWED and (3, 30) in RUN_ALLOWED and (1, 39) in RUN_ALLOWED      # Vermilion, Route 12, Victory Road
    assert POKEMON_CENTER not in RUN_ALLOWED and (10, 0) not in RUN_ALLOWED                   # a Pokémon Center, the Celadon Dept. Store


def test_it_runs_outdoors_with_the_shoes():
    assert client()._can_run(VERMILION) is True


def test_it_walks_without_the_shoes_indoors_on_a_bike_on_water_and_on_the_puzzle_floors():
    assert client(shoes=False)._can_run(VERMILION) is False
    assert client()._can_run(POKEMON_CENTER) is False                      # B does nothing indoors: a press is half a step
    assert client(biking=True)._can_run(VERMILION) is False
    assert client(surfing=True)._can_run(VERMILION) is False
    assert client()._can_run(VICTORY_ROAD_1F) is False                     # boulders are pushed one exact tile
    assert client()._can_run(MANSION_1F) is False                          # switch puzzle floors
    assert client(has_run=False)._can_run(VERMILION) is False              # the legacy http backend has no run_step


def test_the_switch_turns_it_off(monkeypatch):
    import config
    monkeypatch.setattr(config, "USE_RUNNING_SHOES", False)
    assert client()._can_run(VERMILION) is False


def test_a_flag_read_error_means_walk():
    c = client()
    c.reader.read_flag = lambda f: (_ for _ in ()).throw(RuntimeError("no emulator"))
    assert c._can_run(VERMILION) is False
