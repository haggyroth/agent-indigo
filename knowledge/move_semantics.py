"""What moves actually DO in battle (pure; data from the generated knowledge.move_effects).

The old ranker was power × STAB × type. That picks Dream Eater (100) against an awake foe, Fissure never lands,
Hyper Beam every turn, Focus Punch into a hit... This module turns the decomp's per-move `effect` + accuracy into

  * move_score(...)      expected damage per turn, in "power" units, 0 for a move that can't work right now;
  * role_tag(...)        one terse sentence per move for the observation (what it is for, when it fails);
  * catch_setup_hint(..) which of your moves set up a catch (False Swipe, sleep, paralysis, Mean Look).
"""
from knowledge.move_effects import MOVE_FX

# effect -> kind -------------------------------------------------------------------------------------------
_KIND: dict[str, str] = {}


def _k(kind: str, *effects: str) -> None:
    for e in effects:
        _KIND[e] = kind


_k("ohko", "OHKO")
_k("fixed", "LEVEL_DAMAGE", "DRAGON_RAGE", "SONICBOOM", "PSYWAVE", "SUPER_FANG")
_k("reactive", "COUNTER", "MIRROR_COAT", "BIDE", "ENDEAVOR", "REVENGE")
_k("req_foe_asleep", "DREAM_EATER")
_k("req_user_asleep", "SNORE", "SLEEP_TALK")
_k("charge", "SOLAR_BEAM", "RAZOR_WIND", "SKULL_BASH", "SKY_ATTACK")
_k("semi_inv", "SEMI_INVULNERABLE")
_k("focus", "FOCUS_PUNCH")
_k("recharge", "RECHARGE")
_k("friend_high", "RETURN")
_k("friend_low", "FRUSTRATION")
_k("flail", "FLAIL")
_k("eruption", "ERUPTION")
_k("hidden_power", "HIDDEN_POWER")
_k("suicide", "EXPLOSION")
_k("false_swipe", "FALSE_SWIPE")
_k("trap_dmg", "TRAP")
_k("future", "FUTURE_SIGHT")
_k("multi", "MULTI_HIT", "DOUBLE_HIT", "TWINEEDLE", "TRIPLE_KICK", "BEAT_UP")
_k("recoil", "RECOIL", "DOUBLE_EDGE", "RECOIL_IF_MISS")
_k("rampage", "RAMPAGE", "UPROAR", "ROLLOUT", "RAGE")
# non-damaging roles
_k("mean_look", "MEAN_LOOK")
_k("protect", "PROTECT", "ENDURE")
_k("force_switch", "ROAR")
_k("teleport", "TELEPORT")
_k("noop", "SPLASH")
_k("sleep", "SLEEP", "YAWN")
_k("para", "PARALYZE")
_k("poison", "POISON", "TOXIC")
_k("burn", "WILL_O_WISP")
_k("confuse", "CONFUSE", "SWAGGER", "FLATTER", "TEETER_DANCE")
_k("disable", "DISABLE", "ENCORE", "TAUNT", "TORMENT", "SPITE", "IMPRISON")
_k("heal", "RESTORE_HP", "SOFTBOILED", "MOONLIGHT", "MORNING_SUN", "SYNTHESIS", "SWALLOW")
_k("rest", "REST")
_k("setup", "ATTACK_UP", "ATTACK_UP_2", "DEFENSE_UP", "DEFENSE_UP_2", "SPECIAL_ATTACK_UP", "SPECIAL_ATTACK_UP_2",
   "SPECIAL_DEFENSE_UP_2", "SPEED_UP_2", "BULK_UP", "CALM_MIND", "DRAGON_DANCE", "COSMIC_POWER", "BELLY_DRUM",
   "DEFENSE_CURL", "MINIMIZE", "EVASION_UP", "FOCUS_ENERGY", "CHARGE", "STOCKPILE", "CURSE")
_k("debuff", "ATTACK_DOWN", "ATTACK_DOWN_2", "DEFENSE_DOWN", "DEFENSE_DOWN_2", "SPEED_DOWN", "SPEED_DOWN_2",
   "SPECIAL_DEFENSE_DOWN_2", "ACCURACY_DOWN", "EVASION_DOWN", "TICKLE")
_k("screen", "LIGHT_SCREEN", "REFLECT", "SAFEGUARD", "MIST")
_k("seed", "LEECH_SEED")
_k("substitute", "SUBSTITUTE")
_k("doom", "DESTINY_BOND", "PERISH_SONG", "GRUDGE", "MEMENTO")
_k("weather", "RAIN_DANCE", "SUNNY_DAY", "SANDSTORM", "HAIL")

# What each kind is FOR / when it fails. (text, text_if_trainer) — a single str applies to both.
_TAG = {
    "ohko": "one-hit KO but only 30% base accuracy and it FAILS if the foe is a higher level — not a reliable attack",
    "fixed": "fixed damage (not affected by STAB or super-effective), only type immunity matters",
    "reactive": "only works AFTER the foe hits you (Counter/Mirror Coat/Bide) — useless as an opener",
    "req_foe_asleep": "FAILS unless the foe is asleep",
    "req_user_asleep": "only usable while YOU are asleep",
    "charge": "charges one turn first (2 turns per hit)",
    "semi_inv": "two turns; you can't be hit during the first",
    "focus": "FAILS if you are hit the turn it charges",
    "recharge": "you must recharge next turn (half the real damage per turn)",
    "false_swipe": "never KOs — leaves the foe at 1 HP: the catching move",
    "trap_dmg": "damages and holds the foe 2-5 turns (it can't run or switch)",
    "suicide": "FAINTS YOU — no XP",
    "mean_look": "traps the foe (it can't run or switch): use it BEFORE weakening a wild Pokémon you want to catch",
    "protect": "blocks one turn; FAILS if used twice in a row — never spam it",
    "force_switch": ("blows a WILD foe away: the battle ENDS (no XP, no catch)",
                     "forces a random switch (no XP)"),
    "teleport": ("ESCAPES a wild battle (don't use it to catch)", "does nothing in a trainer battle"),
    "noop": "does nothing",
    "sleep": "puts the foe to sleep (also raises catch odds); FAILS if the foe has a status condition",
    "para": "paralyzes the foe (slower, may skip turns; raises catch odds); fails if the foe has a status condition",
    "poison": "poisons the foe — slow; fails if the foe has a status condition",
    "burn": "burns the foe (halves its Attack); fails if the foe has a status condition",
    "confuse": "confuses the foe",
    "disable": "interferes with the foe's moves for a few turns",
    "heal": "restores ~half your HP",
    "rest": "full heal but you sleep 2 turns",
    "setup": "raises your stats — only worth it in a long, tough fight",
    "debuff": "lowers a foe stat",
    "screen": "protects your side for 5 turns",
    "seed": "drains the foe a little each turn",
    "substitute": "costs 25% HP; a decoy that blocks status moves",
    "doom": "trades your Pokémon for the foe's — situational",
    "weather": "changes the weather for 5 turns",
    "future": "hits 2 turns later",
}


def effect_of(name: str) -> str:
    return MOVE_FX.get(name, ("HIT",))[0]


def accuracy_of(name: str) -> int:
    """Percent; moves that never miss (accuracy 0 in the decomp) read as 100."""
    acc = MOVE_FX.get(name, ("HIT", 100))[1]
    return acc or 100


def kind_of(name: str) -> str:
    return _KIND.get(effect_of(name), "damage")


def role_tag(name: str, *, wild: bool | None = None, foe_asleep: bool = False, user_level: int = 0,
             foe_level: int = 0) -> str:
    """One terse sentence about what `name` does / when it fails ('' for a plain damaging move)."""
    kind = kind_of(name)
    t = _TAG.get(kind)
    if t is None:
        acc = accuracy_of(name)
        return f"{acc}% accurate" if acc < 85 else ""
    if isinstance(t, tuple):
        t = t[0] if wild is not False else t[1]
    if kind == "req_foe_asleep" and foe_asleep:
        return "foe is asleep — works"
    if kind == "ohko" and user_level and foe_level:
        if user_level < foe_level:
            return "FAILS: the foe is a higher level"
        t = f"one-hit KO, {min(100, 30 + user_level - foe_level)}% chance to hit (30% base + level difference)"
    return t


# damage scoring ---------------------------------------------------------------------------------------------
def _power_equivalent(damage: float, level: int) -> float:
    """Express a flat `damage` as the base power of a neutral attack from a `level` mon (A/D = 1)."""
    lvl = level or 50
    return max(0.0, damage - 2) * 50.0 / (2 * lvl / 5 + 2)


def _flail_power(hp_frac: float) -> int:
    px = int(max(0.0, min(1.0, hp_frac)) * 48)
    return 200 if px <= 1 else 150 if px <= 4 else 100 if px <= 9 else 80 if px <= 16 else 40 if px <= 32 else 20


def move_score(name: str, attacker_types=(), defender_types=(), *, user_level: int = 0, foe_level: int = 0,
               foe_asleep: bool = False, friendship: int = 70, user_hp_frac: float = 1.0, foe_hp: int = 0) -> float:
    """Expected damage per turn in base-power units (0 = this move does nothing useful as an attack right now).

    power × accuracy × STAB × type effectiveness, with the exceptions that matter: one-hit KOs and reactive moves
    are never auto-picked; Dream Eater needs a sleeping foe; two-turn and recharge moves count half; Return /
    Frustration use friendship (a fresh catch has ~70); fixed-damage moves use their real damage and ignore STAB and
    super-effectiveness; Flail/Eruption use your HP; Focus Punch and Explosion are never auto-picked."""
    from knowledge.battle import effectiveness_vs
    from knowledge.leafgreen_data import MOVE_POWER, MOVE_TYPE
    kind = kind_of(name)
    if kind in ("ohko", "reactive", "req_user_asleep", "focus", "suicide"):
        return 0.0
    if kind == "req_foe_asleep" and not foe_asleep:
        return 0.0
    power = float(MOVE_POWER.get(name, 0))
    if kind == "friend_high":
        power = friendship * 10 / 25
    elif kind == "friend_low":
        power = (255 - friendship) * 10 / 25
    elif kind == "flail":
        power = _flail_power(user_hp_frac)
    elif kind == "eruption":
        power = max(1.0, 150 * user_hp_frac)
    if power <= 0:
        return 0.0
    mtype = MOVE_TYPE.get(name)
    eff = 1.0
    if kind != "hidden_power" and mtype and defender_types:      # Hidden Power's real type comes from IVs
        eff = effectiveness_vs(mtype, tuple(defender_types))
    if eff == 0:
        return 0.0
    acc = accuracy_of(name) / 100.0
    if kind == "fixed":
        fx = effect_of(name)
        if fx in ("LEVEL_DAMAGE", "PSYWAVE") and user_level:
            dmg = float(user_level)
        elif fx == "DRAGON_RAGE":
            dmg = 40.0
        elif fx == "SONICBOOM":
            dmg = 20.0
        elif fx == "SUPER_FANG" and foe_hp:
            dmg = foe_hp / 2
        else:
            return power * acc                                     # level / HP unknown: the table's estimate
        return _power_equivalent(dmg, user_level) * acc
    stab = 1.5 if (mtype in attacker_types and kind != "hidden_power") else 1.0
    score = power * acc * stab * eff
    if kind in ("charge", "semi_inv", "recharge"):
        score *= 0.5
    return score


# catching ---------------------------------------------------------------------------------------------------
def catch_setup_hint(move_names, pp=None) -> str:
    """Which of your moves help a catch, or '' — False Swipe first, then sleep/paralysis, then Mean Look."""
    have = {}
    for i, n in enumerate(move_names or []):
        if not n or (pp is not None and i < len(pp) and pp[i] <= 0):
            continue
        have.setdefault(kind_of(n), n)
    bits = []
    if "false_swipe" in have:
        bits.append(f"{have['false_swipe']} (leaves it at 1 HP, never KOs)")
    if "sleep" in have:
        bits.append(f"{have['sleep']} (sleep ≈ best catch bonus)")
    if "para" in have:
        bits.append(f"{have['para']} (paralysis helps)")
    if "mean_look" in have:
        bits.append(f"{have['mean_look']} (so it can't run)")
    return ("Catch setup you have: " + "; ".join(bits) + ".") if bits else ""
