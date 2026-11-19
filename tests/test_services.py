"""rename_pokemon and daycare refusals (#277, no emulator): bad names, unknown Pokémon, a one-mon party, a full party — all answered before any travel."""
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402


def mon(name, nick="", hp=20):
    return NS(species_name=name, nickname=nick, move_names=["Tackle"], species_id=1, level=20, current_hp=hp, max_hp=20)


def client(party, money=1000):
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_party=lambda: party, detect_context=lambda: NS(name="OVERWORLD"), read_money=lambda: money)
    c._go_to = lambda *a, **k: pytest.fail("should have refused before travelling")
    return c


def test_rename_refuses_untypeable_overlong_and_unchanged_names_before_travelling():
    c = client([mon("Venusaur"), mon("Pidgeotto", "Sky High")])
    assert "can't be typed" in c._rename_pokemon("Pidgeotto", "Kyle@!#")
    assert "can't be typed" in c._rename_pokemon("Pidgeotto", "WayTooLongNickname")
    assert "can't be typed" in c._rename_pokemon("Pidgeotto", "  ")
    assert "already called" in c._rename_pokemon("Pidgeotto", "Sky High")


def test_rename_names_an_unknown_pokemon_instead_of_guessing():
    out = client([mon("Venusaur")])._rename_pokemon("Charizard", "Blaze")
    assert "Charizard" in out or "No Pokémon" in out or "party" in out.lower()


def test_daycare_needs_a_known_action_and_a_second_fighter():
    c = client([mon("Venusaur")])
    assert "action='deposit'" in c._daycare("fly")
    assert "another one in your party can still battle" in c._daycare("deposit", "Venusaur")
    only_one_alive = client([mon("Venusaur"), mon("Pidgeotto", hp=0)])
    assert "another one in your party can still battle" in only_one_alive._daycare("deposit", "Venusaur")
    assert "fainted" in client([mon("Venusaur", hp=0), mon("Pidgeotto")])._daycare("deposit", "Venusaur")


def test_daycare_withdraw_needs_room_in_the_party():
    assert "party is full" in client([mon(f"M{i}") for i in range(6)])._daycare("withdraw")
