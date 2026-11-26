"""The only RAM the agent may write (#375).

The design rule is that the emulator is *read* for truth and written ONLY to point a menu cursor at the choice a skill has already made —
never battle outcomes, RNG, party data, bag, money or save data. This module turns the rule into code: `NativeMGBAClient.write8/16/32`
call `check()` and a write outside these ranges raises `WriteNotAllowed` (tests/live stages memory on purpose and opts out with
`client.unrestricted_writes = True`).

Every entry says why it is safe. Adding a write site means adding a range here and its call site to `tests/test_write_guard.py`.
"""
from game.constants import Addr
from game.options import OPTIONS_OFFSET


class WriteNotAllowed(ValueError):
    """A skill tried to write memory that is not on the allow-list."""


# (name, start, length, why it is allowed)
STATIC_RANGES: tuple[tuple[str, int, int, str], ...] = (
    ("MOVE_CURSOR", Addr.MOVE_CURSOR, 1, "gMoveSelectionCursor: the FIGHT menu slot A will commit (use_move)"),
    ("ACTION_CURSOR", Addr.ACTION_CURSOR, 1, "gActionSelectionCursor: FIGHT/BAG/POKEMON/RUN (and the Safari menu) cursor; a static battle global, "
                                             "also pointed at FIGHT before an advance A (harmless outside the action menu)"),
    ("SHOP_ITEMLIST_PTR", Addr.SHOP_DATA + Addr.SHOP_ITEMLIST, 4, "sShopData.itemList pointer, zeroed before opening a Mart so a stale list cannot read as "
                                                               "'this clerk's menu is up' (UI scratch state, not game data)"),
)

# The one write that is not a cursor: the in-game Option 'Battle Style' bit (SHIFT gives the free switch after a trainer's Pokémon faints). It lives in
# SaveBlock2, which moves, so it is checked against the live pointer. It is a settings bitfield the player could set from the Option menu; it is not
# progress, stats or RNG.
OPTIONS_RANGE = ("OPTIONS_BITFIELD", OPTIONS_OFFSET, 2, "SaveBlock2.options: battle style (game/options.py apply_battle_style)")


def check(address: int, width: int, saveblock2: int = 0) -> str:
    """Name of the allow-list entry covering [address, address+width), or raise WriteNotAllowed. `saveblock2` is the live SaveBlock2 pointer (0 = unreadable)."""
    end = address + width
    for name, start, length, _why in STATIC_RANGES:
        if start <= address and end <= start + length:
            return name
    if 0x02000000 <= saveblock2 < 0x02040000:
        name, off, length, _why = OPTIONS_RANGE
        if saveblock2 + off <= address and end <= saveblock2 + off + length:
            return name
    raise WriteNotAllowed(
        f"write of {width} byte(s) at {address:#010x} is not on the allow-list (game/write_guard.py): the agent only writes menu cursors "
        f"and the battle-style option, never game state")
