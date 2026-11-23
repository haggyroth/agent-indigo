"""PP restoring items (pure): which Pokémon / move needs them, and how the Bag menus are driven.

Ether / Max Ether restore ONE move (the game opens a move-select screen after the Pokémon is chosen); Elixir / Max Elixir restore every move of one Pokémon. Neither is sold in a Kanto Mart —
they are only found — so a run that picks one up has to use it where it matters: the Elite Four's sealed rooms, where "Thunder has no PP left" ends a fight."""
from knowledge.move_data import MOVE_DATA

ETHER, MAX_ETHER, ELIXIR, MAX_ELIXIR = 34, 35, 36, 37
ONE_MOVE = frozenset({ETHER, MAX_ETHER})
ALL_MOVES = frozenset({ELIXIR, MAX_ELIXIR})
PP_ITEMS = ONE_MOVE | ALL_MOVES


def move_deficits(mon) -> list[int]:
    """Per move slot: PP missing against the move's base maximum (PP Ups are not read, so a boosted move may show a deficit of 0 early). 0 for an empty slot."""
    names = getattr(mon, "move_names", None) or []
    pps = getattr(mon, "pp", None) or []
    out = []
    for i in range(4):
        name = names[i] if i < len(names) else ""
        cur = pps[i] if i < len(pps) else 0
        top = MOVE_DATA.get(name, (0, "", 0))[2] if name else 0
        out.append(max(0, top - cur) if name else 0)
    return out


def pick_pp_target(party, iid: int) -> int | None:
    """0-based slot of the Pokémon that gains most from this PP item (Elixirs: the biggest total deficit; Ethers: the biggest single-move deficit, damaging moves first), None if nobody is short."""
    best, slot = 0, None
    for i, p in enumerate(party):
        if getattr(p, "current_hp", 1) <= 0:
            continue
        d = move_deficits(p)
        score = sum(d) if iid in ALL_MOVES else max(d, default=0)
        if score > best:
            best, slot = score, i
    return slot


def pick_move(mon, wanted: str = "") -> int:
    """Move slot (0-based) for an Ether: the named move if given and known, else the one with the biggest deficit — a damaging move before a status move when they tie."""
    names = [n for n in (getattr(mon, "move_names", None) or [])]
    if wanted:
        low = wanted.strip().lower()
        for i, n in enumerate(names):
            if n and n.lower() == low:
                return i
        for i, n in enumerate(names):
            if n and low in n.lower():
                return i
    d = move_deficits(mon)
    return max(range(4), key=lambda i: (d[i], MOVE_DATA.get(names[i], (0,))[0] > 0 if i < len(names) and names[i] else False, -i))
