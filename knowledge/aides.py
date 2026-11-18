"""Prof. Oak's Aides trade items for Pokédex counts (pure data; no I/O).

Three aides (decomp Route2_EastBuilding, Route11_EastEntrance_2F, Route15_WestEntrance_2F) all compare the number of species CAUGHT (GetPokedexCount puts the seen
count in VAR_0x8005 and the caught count in VAR_0x8006, and every script tests 0x8006 — the Route 2 text calls it "complete data on ten species"):
10 caught → HM05 Flash, 30 → the Itemfinder, 50 → the Exp. Share. `ready` says which rewards are claimable now."""

# (quest key, species caught needed, flag set when the item is received, label)
AIDES = (
    ("flash", 10, 0x23B, "HM05 Flash"),
    ("itemfinder", 30, 0x252, "the Itemfinder"),
    ("exp_share", 50, 0x256, "the Exp. Share"),
)


def ready(caught: int, flag_set) -> list:
    """[(key, label, needed)] of the aide rewards whose count is met and which are not yet collected. `flag_set(flag) -> bool`."""
    return [(k, label, need) for k, need, flag, label in AIDES if caught >= need and not flag_set(flag)]


def next_reward(caught: int, flag_set):
    """(label, species still to catch) for the next uncollected reward whose count is NOT yet met, or None."""
    left = [(need - caught, label) for k, need, flag, label in AIDES if caught < need and not flag_set(flag)]
    return (left[0][1], left[0][0]) if left else None
