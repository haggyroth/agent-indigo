"""When a cartridge save is due (pure) and how it reaches the readiness block."""
from types import SimpleNamespace as P

from knowledge.readiness import SAVE_EVERY_BATTLES, assess, battles_total, render, save_note


def test_never_saved_is_only_worth_mentioning_once_there_is_progress():
    assert save_note(0, 2, None, 0) == ""
    assert "never saved" in save_note(0, 5, None, 0) and "never saved" in save_note(1, 0, None, 0)


def test_a_new_badge_or_a_pile_of_fights_makes_a_save_due():
    assert save_note(3, 10, 3, 10) == ""
    assert "1 badge(s)" in save_note(3, 10, 2, 10)
    assert save_note(3, 10 + SAVE_EVERY_BATTLES - 1, 3, 10) == ""
    assert f"{SAVE_EVERY_BATTLES} battles since" in save_note(3, 10 + SAVE_EVERY_BATTLES, 3, 10)


def test_battles_total_sums_every_outcome():
    assert battles_total({"battles_won": 3, "battles_lost": 1, "battles_fled": 2, "battles_caught": 4, "total_battles": 99}) == 10


def test_readiness_names_save_game_but_never_ahead_of_a_must():
    mon = P(species_id=1, species_name="Bulbasaur", nickname="", level=20, max_hp=40, current_hp=40, move_names=["Tackle"],
            move_ids=[33], pp=[35, 0, 0, 0], status="healthy", ivs=(), held_item=0)
    text = render(assess([mon] * 4, balls=10, potions=5, money=0, save_due="you earned 1 badge(s) since the last save"))
    assert "save_game()" in text and "save_state only keeps emulator slots" in text
    hurt = P(**{**mon.__dict__, "current_hp": 3})
    assert "save_game()" not in render(assess([hurt] * 4, balls=10, potions=5, save_due="you have never saved the game"))
