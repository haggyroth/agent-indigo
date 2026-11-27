"""The Trainer Tower driver's constants and refusals (#369), against a fake game."""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.skills import ttower
from game.state import GameContext

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402


def test_the_scene_var_and_maps_match_the_decomp_constants():
    vars_h = Path("~/Projects/pokefirered/include/constants/vars.h").expanduser()
    if vars_h.exists():
        m = re.search(r"VAR_MAP_SCENE_TRAINER_TOWER\s+(0x[0-9A-Fa-f]+)", vars_h.read_text())
        assert int(m.group(1), 16) == ttower.VAR_TOWER_SCENE
    assert ttower.LOBBY == (2, 10) and ttower.ROOF == (2, 9) and ttower.FLOORS == tuple((2, n) for n in range(1, 9))
    assert ttower.TYPES == {"single": 0, "double": 1, "knockout": 2, "mixed": 3} and len(ttower.TYPE_NAMES) == 4


def _client(prizes=(False,) * 4, ctx=GameContext.OVERWORLD, map_=(3, 5)):
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_trainer_tower=lambda: [{"prize": p, "floors": 0, "best": 215999} for p in prizes], detect_context=lambda: ctx, read_current_map=lambda: map_)
    return c


def test_without_a_type_it_explains_and_lists_the_prizes():
    out = _client()._trainer_tower("")
    assert "Trainer Tower prizes: 0/4" in out and "single|double|knockout|mixed" in out
    assert "(Single, Mixed)" in _client((True, False, False, True))._trainer_tower("")


def test_a_won_challenge_is_not_repeated_and_a_battle_or_menu_blocks_the_start():
    assert "already won" in _client((True, False, False, False))._trainer_tower("single")
    assert "finish it first" in _client(ctx=GameContext.IN_BATTLE)._trainer_tower("double")
    assert "open field" in _client(ctx=GameContext.IN_MENU)._trainer_tower("double")
