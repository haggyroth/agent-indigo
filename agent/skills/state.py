"""Every piece of state the skills keep between tool calls, declared in ONE place (#214).

It used to be implicit: a mixin would write `self._trip = …` somewhere and another would read `getattr(self, "_trip", None)`, or
reach into `self.__dict__.setdefault("_trainer_losses", {})`. Nothing said which skill owned a field, what its default was, or
when it reset (`_travel_fights` was reset in one place only). `SkillState` is the contract: AgentClient inherits it, each field
has a default here and an owner and meaning below, and a skill reads it as a plain attribute — no `getattr` fallbacks.

Immutable defaults are class attributes; the two per-instance dicts use `lazy`, which builds the dict on first use.
"""


class lazy:
    """A per-instance default built on first access (a class attribute would be shared by every client)."""

    def __init__(self, factory):
        self.factory = factory
        self.name = ""

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        value = obj.__dict__[self.name] = self.factory()
        return value


class SkillState:
    # ── nav: travel (go_to / go_to_map / challenge_leader) ───────────────────────────────────────
    _trip = None                 # {"dest", "target", "call"?} of a trip an encounter interrupted; cleared on arrival / a new go_to
    _go_depth = 0                # nesting of _go_to (re-entrancy guard, MAX_TRIP_DEPTH); always unwinds to 0
    _stop_reason = None          # why the current trip stopped (set by _stop, read by the _go_to wrapper)
    last_trip_stop = None        # {"reason", "target", "map"} of the last outermost trip (also emitted as a `trip` event)
    _go_to_last_end = None       # map where the previous trip ended …
    _go_to_stalls = 0            # … and how many consecutive trips ended there without arriving (story-gated stall detection)
    _in_puzzle = False           # a gym/cave puzzle solver is running (don't recurse into it)
    _in_town_visit = False       # first-visit town heal in progress
    _surf_retry = False          # one Surf retry per trip
    _gym_warned = None           # gym map where the under-levelled warning was already given (a 2nd call proceeds)
    _balance_warned = None       # …and the lopsided-team warning
    _trainer_losses = lazy(dict)  # {map: n} lost trainer battles per map (a mandatory trainer beating an under-levelled team)
    _edge_fail = lazy(dict)       # {(map, direction): n} seamless-edge crossings that failed
    _avoid_maps = ()              # maps travel must not route through (the Safari Zone quest keeps clear of its own exit)

    # ── overworld: grind / heal / shop ──────────────────────────────────────────────────────────
    _grind_run = None            # the grind session in progress (None = none); abandoned by any other travel tool
    _training_swapped = False    # the ace is benched behind a lagging lead until the session ends (see _grind_finish)
    _wander_dir = "Up"           # heading while wandering the grass
    _slot_trace = None           # a list while debugging the slot driver: one record per reel stop (state, wait, where it landed)

    # ── battle ──────────────────────────────────────────────────────────────────────────────────
    _status_streak = (None, 0)   # (status, turns) so a long-lasting status is not re-explained every turn
    _nick_refused = None         # nickname the naming screen refused, so catch() does not retry the same one
    _current_opponent = ""       # main.py hands the foe name to the client here (and clears it); battle reads it as a fallback

    # ── move learning (level-up move offers) ─────────────────────────────────────────────────────
    _learn_armed = False         # armed on a lead level-up edge, disarmed after driving (never re-engage on a stale value)
    _levels_seen = None          # {species_id: summed levels}: a level-up is a rise for the SAME species
    _offer_resolved = 0          # last move-offer id already declined/accepted (gMoveToLearn LINGERS after a decline)
    _learn_in_battle = False     # this battle's lingering-offer baseline has been taken

    # ── quests / menus ──────────────────────────────────────────────────────────────────────────
    _vermilion_cans = None       # (can1, can2) read once: a gym trainer's battle can interrupt the switch puzzle mid-way
    _menu_driver = None          # lazily built MenuDriver (MenuMixin._menus)
