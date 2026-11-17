"""When a Repel is the right call (pure). Repel keeps off every wild Pokémon whose level is at or below the lead's, for 100 / 200 /
250 steps (Repel / Super / Max). Since go_to hands each wild encounter to the model, a Repel is the cheap answer to routes full of
Pokémon that are no use: too weak to train on, nothing worth catching, and a party that just wants to get somewhere."""
from knowledge.encounters import LAND_LEVELS

VAR_REPEL_STEP_COUNT = 0x4020
REPEL_IDS = (86, 83, 84)               # Repel, Super Repel, Max Repel (cheapest first)
MIN_TEAM = 4                           # a smaller team should be catching, not repelling


def note(cur, lead_level: int, steps_left: int, repels: int, team_size: int, wanted_here: bool = False) -> str:
    """One observation line, or ''."""
    if steps_left > 0:
        return f"Repel active: {steps_left} steps left (wild Pokémon up to L{lead_level} stay away)."
    rng = LAND_LEVELS.get(tuple(cur))
    if not repels or rng is None or team_size < MIN_TEAM or wanted_here or lead_level < rng[2]:
        return ""
    return (f"Every wild Pokémon here is L{rng[2]} or lower and your lead is L{lead_level}: use_item('Repel') keeps them off while you "
            "travel (skip it if you want to catch or train here).")
