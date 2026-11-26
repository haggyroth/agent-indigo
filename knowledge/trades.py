"""The in-game NPC trades of Kanto (pure data; every row read from the decomp — src/data/ingame_trades.h and each trader's map script — #362).

Each trader wants ONE species from your party and gives theirs (level-matched, a nickname and a different OT: it evolves normally, and the Pokémon obeys at any level). One trade each, ever
(a FLAG_DID_*_TRADE). `dex_sources.TRADES` says who wants what; this adds where the NPC stands and the flag. The two Nidoran trades differ between FireRed and LeafGreen and are not here."""

# received species id -> (wanted species id, map (group, num), NPC tile, FLAG_DID_*_TRADE, where)
NPC_TRADES: dict[int, tuple[int, tuple, tuple, int, str]] = {
    83: (21, (9, 4), (4, 4), 0x24D, "Vermilion City, house 2"),                 # Farfetch'd for a Spearow
    86: (77, (12, 4), (11, 8), 0x276, "Cinnabar Pokémon Lab, the experiment room"),    # Seel for a Ponyta
    101: (26, (12, 2), (4, 6), 0x274, "Cinnabar Pokémon Lab, the lounge"),        # Electrode for a Raichu
    108: (55, (26, 1), (5, 3), 0x257, "Route 18 gatehouse, 2F"),                  # Lickitung for a Golduck
    114: (48, (12, 2), (10, 5), 0x275, "Cinnabar Pokémon Lab, the lounge"),       # Tangela for a Venonat
    122: (63, (15, 1), (7, 2), 0x248, "Route 2 house (the scientist)"),           # Mr. Mime for an Abra
    124: (61, (7, 2), (2, 2), 0x24A, "Cerulean City, house 3"),                   # Jynx for a Poliwhirl
}


def find(query: str, names: dict) -> int | None:
    """Received species id for a name (case / punctuation tolerant, unique prefix ok); None when it matches no trade."""
    q = "".join(ch for ch in str(query).lower() if ch.isalnum())
    if not q:
        return None
    norm = {sid: "".join(ch for ch in names.get(sid, "").lower() if ch.isalnum()) for sid in NPC_TRADES}
    exact = [sid for sid, n in norm.items() if n == q]
    hits = exact or [sid for sid, n in norm.items() if n.startswith(q)]
    return hits[0] if len(hits) == 1 else None
