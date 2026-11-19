"""Nickname rules (pure). The MODEL invents the names; this module makes sure the one it chose can actually be typed on the Gen III naming
keyboard and isn't a bland non-name, and offers a varied POOL of ideas (dad jokes, food, pets, titles, objects — nothing to do with the species) to
hint from and to fall back on, so a rejected or untypeable pick still ends with a good name instead of a stuck keyboard."""
import random
import re
import unicodedata

MAX_NAME = 10
# Keys the naming driver can type (game/naming.py): letters, digits, space, '.', ',', '!', '?'.
_ALLOWED = re.compile(r"[^A-Za-z0-9 .,!?]")
_FANCY = {"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "&": " and "}


def _clean(name: str) -> str:
    s = (name or "").strip()
    for k, v in _FANCY.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[-_/]+", " ", s)
    s = _ALLOWED.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def sanitize(name: str) -> str:
    """Best-effort conversion of what the model wrote into something typeable: accents folded
    (Pokémon → Pokemon), '-' '_' '/' become spaces, anything else untypeable is dropped, runs of
    spaces collapse, and it is cut to 10 characters. May return '' (nothing usable)."""
    return _clean(name)[:MAX_NAME].strip()


def shorten(name: str) -> str:
    """A name that is too long for the keyboard, cut down to fit: whole words while at least 5 characters survive ('Beaky Blinders' -> 'Beaky'), else a plain cut ('Hyperactive Beast' -> 'Hyperactiv')."""
    full = _clean(name)
    if len(full) <= MAX_NAME:
        return full
    words, out = full.split(" "), ""
    for w in words:
        nxt = (out + " " + w).strip()
        if len(nxt) > MAX_NAME:
            break
        out = nxt
    return out if len(out) >= 5 else full[:MAX_NAME].strip()


POOL = (
    # dad energy / titles
    "Zap Daddy", "Big Dave", "Uncle Stu", "Coach", "Sarge", "The Duke", "Dr. Pain", "Mr. Boots", "Mrs. Doyle", "Sir Loin", "Lord Gus",
    "The Mayor", "Captain", "Admiral", "Professor", "Duchess", "Baron", "Maestro", "Chief", "Boss", "Champ", "Rookie", "Legend", "Ace",
    # food
    "Nugget", "Biscuit", "Waffles", "Pickles", "Meatball", "Noodle", "Tater Tot", "Muffin", "Gravy", "Pancake", "Taco", "Nacho", "Burrito",
    "Sushi", "Pretzel", "Cupcake", "Bagel", "Dumpling", "Mochi", "Churro", "Brisket", "Chowder", "Gumbo", "Pepper", "Ginger", "Cookie",
    "Cheddar", "Brie", "Wasabi", "Kimchi", "Falafel", "Hummus", "Crouton", "Pierogi", "Gnocchi", "Biscotti",
    # pets and book people
    "Hobbes", "Gizmo", "Waldo", "Chewie", "Yoda", "Sparky", "Rascal", "Scooby", "Bandit", "Rufus", "Ziggy", "Bruiser", "Mavis", "Gertrude",
    "Percy", "Winston", "Ozzy", "Frodo", "Gandalf", "Bilbo", "Sherlock", "Watson", "Hamlet", "Macbeth", "Gatsby", "Atticus", "Ahab", "Yossarian",
    # silly sounds and words
    "Sir Wiggle", "Dusty Boot", "Zappy Boy", "Sky High", "Mole Hill", "Beep Boop", "Wobbles", "Noodles", "Squish", "Bonk", "Doink", "Kaboom",
    "Zoinks", "Yeet", "Floof", "Snoot", "Boop", "Fuzzbutt", "Chonk", "Gooby", "Bean", "Pudge", "Stompy", "Biteson", "Nibbles", "Sneezy", "Grumble",
    "Kapow!", "Bazinga!", "Yahoo!", "Huzzah!", "Oh No!", "Why Me?", "Eureka!", "Oops!", "Whoa!", "Hmm.",
    # ordinary human names
    "Steve", "Brenda", "Kevin", "Karen", "Dennis", "Linda", "Gordon", "Phil", "Doug", "Larry", "Bob", "Marge", "Todd", "Randy", "Carl", "Trevor",
    "Chad", "Brad", "Greg", "Janet", "Tiffany", "Ricardo", "Dmitri", "Svetlana", "Bjorn", "Pierre", "Giuseppe", "Gary Jr.", "Moose", "Bubba",
    "Tank", "Slim", "Tiny", "Mac", "Rocky",
    # tech and space
    "Pixel", "Glitch", "Byte", "Turbo", "Rocket", "Comet", "Nova", "Orbit", "Laser", "Widget", "Bolt", "Sprocket", "Cog", "Ping", "Modem",
    "Dial Up", "Wi Fi",
    # places
    "Toledo", "Fresno", "Omaha", "Tuscany", "Brooklyn", "Reno", "Boise", "Waco", "Tulsa", "Dayton",
    # household objects and instruments
    "Sock", "Spatula", "Doorknob", "Lampshade", "Stapler", "Toaster", "Pillow", "Spoon", "Banjo", "Kazoo", "Tuba", "Bongo", "Maraca", "Ukulele",
    # cool
    "Shadow", "Razor", "Viper", "Maverick", "Goose", "Iceman", "Havoc", "Rogue", "Phantom", "Blaze",
)


def usable(name: str, taken=()) -> bool:
    """Can `name` be typed and kept as is: at least two letters/digits, within the limit, not already on the team."""
    full = _clean(name)
    if not 2 <= len(full) <= MAX_NAME or sum(c.isalnum() for c in full) < 2:
        return False
    return full.lower() not in {t.lower().strip() for t in taken if t}


def suggest(species_name: str = "", taken=(), k: int = 4, rng=None) -> list[str]:
    """`k` different nicknames from the POOL that nothing on the team already uses and that are not the species name — a fresh draw each call."""
    rng = rng or random
    avoid = {t.lower().strip() for t in taken if t} | {(species_name or "").lower()}
    free = [n for n in POOL if n.lower() not in avoid]
    return rng.sample(free, min(k, len(free)))


def pick(species_name: str = "", taken=(), rng=None) -> str:
    """One random pool nickname (the fallback when the model's own pick can't be used)."""
    out = suggest(species_name, taken, 1, rng)
    return out[0] if out else "Buddy"


def critique(name: str, species_name: str = "", taken=()) -> str | None:
    """Why `name` is a poor pick (so the model should try again), or None if it's fine.
    Poor = empty/one character, too long for the keyboard, just the species name (± a number),
    or already used on the team."""
    full = _clean(name)
    if len(full) < 2:
        return "that name is empty or a single character"
    if sum(c.isalnum() for c in full) < 2:
        return f"'{full}' needs at least two letters or digits"
    if len(full) > MAX_NAME:
        return f"'{full}' is {len(full)} characters — the limit is {MAX_NAME}, so shorten it yourself"
    low = full.lower()
    squash = lambda t: re.sub(r"[\s\d]+", "", t.lower())
    if species_name and squash(low) == squash(species_name):
        return f"'{full}' is just the species name (with or without a number)"
    if low in {t.lower().strip() for t in taken if t}:
        return f"'{full}' is already on your team"
    return None
