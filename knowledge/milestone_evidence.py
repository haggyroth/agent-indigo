"""What the game itself says about a story milestone (#379) — pure data.

`record_milestone` lets the model write story facts into long-term memory, and the phase / route guidance (knowledge.navigation.derive_phase) and the Oak's-parcel
beat read them back. A milestone that the cartridge can confirm is only recorded when it does; the few with no RAM signal stay model-asserted (and are marked so).
Done-specs use the story chain's vocabulary: ("flag", id) · ("item", key-item id) · ("badge", bit) · ("party", min size); ANY listed spec is enough.
"""
from knowledge.leafgreen_data import BADGE_BIT_MILESTONE
from knowledge.story_beats import POKE_FLUTE, SILPH_SCOPE

EVIDENCE: dict[str, tuple] = {
    "starter_chosen": (("party", 1),),
    "delivered_oaks_parcel": (("flag", 0x829),),                 # FLAG_SYS_POKEDEX_GET
    "got_cut": (("flag", 0x237),),                               # the same flags the story beats trust (knowledge/story_beats.py)
    "got_flash": (("flag", 0x23B),),
    "got_fly": (("flag", 0x238),),
    "got_surf": (("flag", 0x239),),
    "got_strength": (("flag", 0x23A),),
    "got_silph_scope": (("item", SILPH_SCOPE),),
    "rescued_mr_fuji": (("flag", 0x23C),),
    "got_poke_flute": (("flag", 0x23D), ("item", POKE_FLUTE)),
    "woke_snorlax_12": (("flag", 0x253),),
    # no RAM signal found for these: cleared_rock_tunnel, woke_snorlax_16 (stay model-asserted)
}
EVIDENCE.update({milestone: (("badge", bit),) for bit, milestone in BADGE_BIT_MILESTONE.items()})      # beat_brock … beat_giovanni: the badge byte


def is_verifiable(name: str) -> bool:
    return name in EVIDENCE


def verify(name: str, check) -> tuple[bool, str]:
    """(ok, why-not). `check(spec) -> bool` evaluates one done-spec against the live game. A milestone with no evidence is ok (model-asserted)."""
    specs = EVIDENCE.get(name)
    if not specs:
        return True, ""
    if any(check(s) for s in specs):
        return True, ""
    wants = " or ".join({"flag": "the game flag", "item": "the key item", "badge": "the badge", "party": "a Pokémon in the party"}[k] + (f" {v:#x}" if k == "flag" else f" #{v}" if k in ("item", "badge") else "") for k, v in specs)
    return False, f"the game does not confirm '{name}' yet (it checks {wants}). Record it after it really happens."
