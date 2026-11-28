"""The trade screen's cursor search (game/link.py): pure, no emulator."""
import pytest

from game.link import LEFT, LinkError, UP, _CANCEL, _cursor_path


def test_a_party_of_one_or_two_reaches_cancel_with_one_up():
    assert _cursor_path(0, _CANCEL, 2, 2) == [UP]
    assert _cursor_path(0, _CANCEL, 1, 1) == [UP]


def test_a_bigger_party_goes_over_to_the_partner_first():
    # Up from slot 0 lands on the player's own bottom row; Cancel is reached from the partner's column.
    assert _cursor_path(0, _CANCEL, 3, 2) == [LEFT, UP]


def test_every_party_size_can_reach_cancel_from_slot_zero():
    for own in range(1, 7):
        for other in range(1, 7):
            path = _cursor_path(0, _CANCEL, own, other)
            assert 1 <= len(path) <= 3, (own, other, path)


def test_no_pokemon_no_route():
    with pytest.raises(LinkError):
        _cursor_path(0, 5, 1, 1)                 # slot 5 holds nothing with a party of one
