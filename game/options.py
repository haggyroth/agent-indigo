"""The in-game Option menu settings the agent pins by writing SaveBlock2 directly (no menu driving).

SaveBlock2 +0x14 is a u16 bitfield: textSpeed:3, windowFrameType:5, sound:1 (bit 8), battleStyle:1 (bit 9; 0 = SHIFT, 1 = SET), battleSceneOff:1 (bit 10).
SHIFT is what gives the player a free switch after a trainer's Pokémon faints ('Will you change POKéMON?')."""
from game.constants import Addr

OPTIONS_OFFSET = 0x14
BATTLE_STYLE_BIT = 1 << 9


def _options_addr(mgba) -> int | None:
    sb2 = mgba.read32(Addr.SAVEBLOCK2_PTR)
    return sb2 + OPTIONS_OFFSET if 0x02000000 <= sb2 < 0x02040000 else None


def apply_battle_style(mgba, style: str) -> bool:
    """Make the game's Battle Style option `style` ('shift' | 'set'; anything else = leave it). True when this call changed it."""
    if style not in ("shift", "set"):
        return False
    a = _options_addr(mgba)
    if a is None:
        return False
    cur = mgba.read16(a)
    want = (cur | BATTLE_STYLE_BIT) if style == "set" else (cur & ~BATTLE_STYLE_BIT)
    if want == cur:
        return False
    mgba.write16(a, want)
    return True
