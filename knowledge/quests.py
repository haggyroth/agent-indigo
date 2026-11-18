"""The story-quest registry (pure): which scripted quests exist, what each is for and what must come first.

One tool, `quest(name?)`, replaces a top-level tool per story beat (get_ss_ticket, get_cut, …). `quest()` lists what exists and
where you stand; `quest('cut')` runs one. Adding a beat (Silph Scope, Poké Flute, Safari Zone) is a registry entry plus a driver,
not another tool in every prompt."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Quest:
    key: str
    title: str
    why: str
    needs: tuple = ()          # keys that must be done first


QUESTS: tuple[Quest, ...] = (
    Quest("ss_ticket", "SS Anne ticket from Bill (Route 25 → Sea Cottage)",
          "without it Cerulean's south and east exits stay blocked"),
    Quest("cut", "HM01 Cut from the S.S. Anne's Captain, taught to a Pokémon",
          "a Cut tree blocks Vermilion Gym's door", needs=("ss_ticket",)),
    Quest("coin_case", "the Coin Case from the man in the Celadon Restaurant",
          "the Game Corner (slots, coins, the Prize Corner's TMs) refuses you without it"),
    Quest("rocket_hideout", "the Silph Scope from Giovanni in the Rocket Hideout (under the Celadon Game Corner)",
          "the Pokémon Tower's ghosts can't be fought without it — and the tower holds the Poké Flute"),
    Quest("surf", "HM03 Surf from the Safari Zone Secret House (¥500 entry, ~200 of the 600 steps)",
          "Cinnabar Island and every water route need it"),
    Quest("strength", "HM04 Strength: the Safari Zone's Gold Teeth, returned to the Warden in Fuchsia",
          "Victory Road's boulders (and Seafoam's) need it"),
)
BY_KEY = {q.key: q for q in QUESTS}


def resolve(name) -> Quest | None:
    key = str(name or "").lower().strip().replace(" ", "_").replace("-", "_")
    return BY_KEY.get(key) or next((q for q in QUESTS if key and (key in q.key or key in q.title.lower())), None)


def listing(done) -> str:
    """The text `quest()` returns: every quest with ✔ done / ▶ available / … blocked."""
    done = set(done)
    lines = []
    for q in QUESTS:
        if q.key in done:
            lines.append(f"✔ {q.key}: {q.title} — done")
        elif all(n in done for n in q.needs):
            lines.append(f"▶ {q.key}: {q.title} — {q.why}. quest('{q.key}')")
        else:
            lines.append(f"… {q.key}: {q.title} — first: " + ", ".join(f"quest('{n}')" for n in q.needs if n not in done))
    return "Story quests:\n" + "\n".join(lines)
