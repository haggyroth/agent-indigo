"""One way to say "which Pokémon?" (pure). Every tool that takes a party member — switch_pokemon, use_item, give_item, teach_move,
reorder_party, pc_* — used to resolve the string its own way (some ignored nicknames, all silently took the first of two Pidgeys).
`resolve_mon` is the single rule: a 1-based slot, else an exact species / nickname, else a partial one — and when more than one
Pokémon fits, it says so and asks for a slot number instead of guessing."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Pick:
    index: int | None          # 0-based party index, None when nothing (or too much) matched
    error: str = ""            # the sentence to hand the model when index is None


def roster(party) -> str:
    return ", ".join(f"{i + 1}:{(getattr(p, 'nickname', '') or p.species_name)}" for i, p in enumerate(party) if p.species_name)


def resolve_mon(ref, party) -> Pick:
    key = str(ref).lower().strip()
    if not key:
        return Pick(None, f"Which Pokémon? Your party: {roster(party)}.")
    if key.isdigit():
        i = int(key) - 1
        if 0 <= i < len(party):
            return Pick(i)
        return Pick(None, f"There is no slot {key} — you have {len(party)} Pokémon ({roster(party)}).")
    names = [{(getattr(p, "nickname", "") or "").lower(), (p.species_name or "").lower()} - {""} for p in party]
    for matches in ([i for i, n in enumerate(names) if key in n], [i for i, n in enumerate(names) if any(key in x for x in n)]):
        if len(matches) == 1:
            return Pick(matches[0])
        if len(matches) > 1:
            slots = ", ".join(str(i + 1) for i in matches)
            return Pick(None, f"{len(matches)} Pokémon match {ref!r} (slots {slots}) — name one by its slot number. Party: {roster(party)}.")
    return Pick(None, f"Couldn't find {ref!r} in your party: {roster(party)}.")
