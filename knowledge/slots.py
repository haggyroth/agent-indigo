"""The Gen III slot machine, ported from the decomp's slot_machine.c (pure): when pressing A stops a reel in a good place.

How the machine really works (src/slot_machine.c): at the start of every spin it rolls a *bias* (a payout class: none, cherries, …,
Rocket, 7) from its per-machine table; a bias of Rocket or 7 sticks until it pays out. When you press A, the reel does not stop where
it is — `StopReel1/2/3` slide it up to four positions to a place that serves the bias *if one is in reach*, otherwise it slides
at random (or all the way, for a Rocket / 7 bias). So the skill is timing: press A on a frame where a bias-serving position is in reach.
`stop_is_good` replays those functions for the current reel state, and `frames_until_good` says how long to wait.

The state is read from memory by the driver: reel positions (0-20, counting down), sub-pixel step (0-2, one step per frame), the
bias, and which reels are already stopped. Icons: 0=7 1=Rocket 2=Pikachu 3=Psyduck 4=Cherries 5=Magnemite 6=Shellder."""
from knowledge.game_corner_data import PAYOUTS, REEL_ICONS, ROW_ATTRS, SECOND_REEL_PAIRS, THIRD_REEL_LINES

REEL_LENGTH = 21
NONE, CHERRIES2, CHERRIES3, MAGSHELL, PIKAPSY, ROCKET, SEVEN = range(7)
CHERRY = 4
HOT = (ROCKET, SEVEN)                  # biases that persist until they pay out


def icon_has(attr: int, icon: int) -> bool:
    """TestReelIconAttribute."""
    if attr == NONE:
        return icon != CHERRY
    if attr in (CHERRIES2, CHERRIES3):
        return icon == CHERRY
    if attr == MAGSHELL:
        return icon in (5, 6)
    if attr == PIKAPSY:
        return icon in (2, 3)
    if attr == ROCKET:
        return icon == 1
    if attr == SEVEN:
        return icon == 0
    return False


def _wrap(p: int) -> int:
    return p % REEL_LENGTH


def next_pos(positions, subpixel, reel: int) -> int:
    """GetNextReelPosition: where the reel will be on the next step."""
    p = positions[reel]
    if subpixel[reel] != 0:
        p = _wrap(p - 1)
    return p


def advance(positions, subpixel, spinning, frames: int = 1):
    """The reels `frames` frames later (each spinning reel: sub-pixel +1; past 2 it drops one position)."""
    pos, sub = list(positions), list(subpixel)
    for _ in range(frames):
        for r in range(3):
            if spinning[r]:
                sub[r] += 1
                if sub[r] > 2:
                    sub[r] = 0
                    pos[r] = _wrap(pos[r] - 1)
    return pos, sub


def two_reel_check(r0, p0, r1, p1, bias) -> bool:
    """TwoReelBiasCheck: with reels r0@p0 and r1@p1 stopped, can a line serve `bias`?"""
    icons = [7] * 9
    for i in range(3):
        icons[3 * r0 + i] = REEL_ICONS[r0][_wrap(p0 + i)]
        icons[3 * r1 + i] = REEL_ICONS[r1][_wrap(p1 + i)]
    pairs = SECOND_REEL_PAIRS
    if bias == NONE:
        if any(icon_has(CHERRIES2, icons[i]) for i in range(3)):
            return False
        return any(icons[a] == icons[b] for a, b in pairs)
    if bias == CHERRIES2:
        if r0 == 0 or r1 == 0:
            if r0 == 1 or r1 == 1:
                if any(icons[pairs[i][0]] == icons[pairs[i][1]] for i in range(0, 15, 3)):
                    return False
            return any(icon_has(bias, icons[i]) for i in range(3))
        return True
    if bias == CHERRIES3 and (r0 == 2 or r1 == 2):
        return any(icon_has(bias, icons[i]) for i in range(9))
    return any(icons[a] == icons[b] and icon_has(bias, icons[a]) for a, b in pairs)


def one_reel_check(reel, pos, bias, order, positions) -> bool:
    """OneReelBiasCheck: with the two already-stopped reels (`order`) where they are, does stopping `reel` at `pos` serve `bias`?"""
    first = _wrap(positions[order[0]] + 1)
    second = _wrap(positions[order[1]] + 1)
    p = _wrap(pos + 1)
    icons = [0] * 9
    for i in range(3):
        icons[order[0] * 3 + i] = REEL_ICONS[order[0]][first]
        icons[order[1] * 3 + i] = REEL_ICONS[order[1]][second]
        icons[reel * 3 + i] = REEL_ICONS[reel][p]
        first, second, p = _wrap(first + 1), _wrap(second + 1), _wrap(p + 1)
    lines = THIRD_REEL_LINES
    if bias == NONE:
        if any(icon_has(CHERRIES2, icons[i]) for i in range(3)):
            return False
        return not any(icons[a] == icons[b] == icons[c] for a, b, c in lines)
    if bias == CHERRIES2:
        if any(icons[a] == icons[b] and icon_has(bias, icons[a]) for a, b, _c in lines):
            return False
        return any(icon_has(bias, icons[i]) for i in range(3))
    if bias == CHERRIES3:
        return any(icons[a] == icons[b] and icon_has(bias, icons[a]) for a, b, _c in lines)
    return any(icons[a] == icons[b] == icons[c] and icon_has(bias, icons[a]) for a, b, c in lines)


def stop_is_good(stage: int, positions, subpixel, bias: int) -> bool:
    """Would pressing A NOW (on reel `stage` = 0, 1, 2 in the order they are stopped) put the reel somewhere that serves `bias`?
    Reels are stopped left to right, so `stage` is also the reel index and the reels before it are already at rest."""
    nxt = next_pos(positions, subpixel, stage)
    if stage == 0:
        if bias == NONE:
            return True                                           # nothing to serve: any stop will do
        for i in range(3):
            if icon_has(bias, REEL_ICONS[0][_wrap(nxt + 1 + i)]):
                return True
        return any(icon_has(bias, REEL_ICONS[0][_wrap(nxt - i)]) for i in range(4))
    if stage == 1:
        first = _wrap(positions[0] + 1)
        pos = _wrap(nxt + 1)
        for _ in range(5):
            if two_reel_check(0, first, 1, pos, bias):
                return True
            pos = _wrap(pos - 1)
        return False
    for i in range(5):
        if one_reel_check(2, _wrap(nxt - i), bias, (0, 1), positions):
            return True
    return False


def frames_until_good(stage: int, positions, subpixel, spinning, bias: int, limit: int = 126) -> int | None:
    """Frames to wait before pressing A so the stop serves `bias` (0 = press now); None if no frame in two full turns does.

    The reel's "next position" only changes every third frame, so a good stop is a window of (at least) three frames. We aim for the
    MIDDLE of a window whose neighbours are good too, which keeps the press right even when it lands a frame early or late; if only
    a thinner window exists the first good frame is used."""
    good = []
    for f in range(limit + 1):
        pos, sub = advance(positions, subpixel, spinning, f)
        good.append(stop_is_good(stage, pos, sub, bias))
    for f in range(limit - 1):
        if (f == 0 or good[f - 1]) and good[f] and good[f + 1]:
            return f
    return next((f for f in range(limit) if good[f]), None)


def payout_of(icons9) -> int:
    """CalcPayout for a 9-cell grid (reel*3 + row) at a bet of 3: the sum over the five lines."""
    total = 0
    for c1, c2, c3, min_bet in ROW_ATTRS:
        a, b, c = icons9[c1], icons9[c2], icons9[c3]
        if a == CHERRY:
            match = CHERRIES3 if b == CHERRY else CHERRIES2
        elif a == b == c:
            match = {CHERRY: CHERRIES2, 5: MAGSHELL, 6: MAGSHELL, 2: PIKAPSY, 3: PIKAPSY, 1: ROCKET, 0: SEVEN}.get(a, CHERRIES2)
        else:
            match = NONE
        total += PAYOUTS[match]
    return total
