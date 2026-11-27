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
    # ── llm: context budget (agent/lm_studio_client.py _chat, #372) ───────────────────────────────
    _tok_ratio = 1.0             # the server's reported prompt_tokens ÷ our estimate (smoothed): how far estimate_tokens is off for this model
    _learned_budget = 0          # prompt-token ceiling learned from a context-overflow error (0 = none yet); only ever lowered
    # ── nav: travel (go_to / go_to_map / challenge_leader) ───────────────────────────────────────
    _trip = None                 # {"dest", "target", "call"?} of a trip an encounter interrupted; cleared on arrival / a new go_to
    _go_depth = 0                # nesting of _go_to (re-entrancy guard, MAX_TRIP_DEPTH); always unwinds to 0
    _flying_ahead = False        # a go_to is already flying (or walking out to fly): its nested travel must not plan a second flight
    _fly_failed = lazy(set)      # maps a flight toward a destination failed from (the Fly user fainted, a menu would not open): walk from there, don't retry the menus every call
    _stop_reason = None          # why the current trip stopped (set by _stop, read by the _go_to wrapper)
    last_trip_stop = None        # {"reason", "target", "map"} of the last outermost trip (also emitted as a `trip` event)
    _go_to_last_end = None       # map where the previous trip ended …
    _go_to_stalls = 0            # … and how many consecutive trips ended there without arriving (story-gated stall detection)
    _in_puzzle = False           # a gym/cave puzzle solver is running (don't recurse into it)
    _in_town_visit = False       # first-visit town heal in progress
    _surf_retry = False          # one Surf retry per trip
    _league_room = None          # the Elite Four room the last quest('elite_four') call was in (a later arrival at the Plateau's Center from it = a loss)
    _ready_warned = lazy(set)    # story beats whose 'party not ready' warning was already given (a 2nd quest() call proceeds)
    _gym_warned = None           # gym map where the under-levelled warning was already given (a 2nd call proceeds)
    _balance_warned = None       # …and the lopsided-team warning
    _trainer_losses = lazy(dict)  # {map: n} lost trainer battles per map (a mandatory trainer beating an under-levelled team)
    _surf_search = 0              # >0 while _surf's second pass (the elevation-3 shores) walks to a shore: walk_to must not start Surf itself then (it would recurse into the search)
    _nick_pending = False         # a quest left a nickname box open for the model (Lapras): the quest returns the hand-off message
    _sweep_goal = None            # sweep: the flag of the target being walked to — kept across the battles that end a call, so the next call goes on to the SAME target instead of re-picking the nearest from wherever the fight left us (it oscillated between two ends of Mt. Moon B2F)
    _quest_opts = ()              # the words after the quest name in quest('new_game squirtle name=KYLE') — read by the driver that was dispatched
    _pc_fail_streak = 0           # consecutive pc() calls whose storage screen would not open (two in a row: tell the model to stop retrying)
    _stall_log = lazy(dict)       # stall snapshots saved this run (see agent.failure_shots.note_stall): the failing result being repeated, its run length, how many states were saved
    _shot_log = lazy(dict)        # failure screenshots saved this run (see agent.failure_shots): count, last time, results already pictured
    _walk_avoid = None            # tiles walk_to must not cross (set around a gym's teleport-pad walk)
    _lost_goals = lazy(dict)      # {grass map: the party's best level when a trainer on the way to it beat us} — skipped until we are 3 levels stronger
    _gate_why = ""                # the last reason a grass route was skipped (a story gate / a lost trainer), told to the model if grind() then fails
    _exp_share_fails = lazy(dict)  # {(holder, target, party levels): failed Exp. Share moves} — two strikes and that move is not retried until the party changes
    _failed_grass = lazy(dict)    # {grass map: times go_to ended there without arriving (stall / budget)} — 2 strikes and grind stops picking it
    _shift_offered = False        # the trainer's 'Will you change POKéMON?' box (Battle Style SHIFT) was already put to the model: a 2nd look declines it
    _sealed_grass = lazy(set)     # maps whose only grass is walled off (a Cut-tree pocket) and the party cannot Cut: skip them
    _edge_fail = lazy(dict)       # {(map, direction): n} seamless-edge crossings that failed
    _avoid_maps = ()              # maps travel must not route through (the Safari Zone quest keeps clear of its own exit)
    _vr_floor = None              # Victory Road: the floor whose boulders _vr_known describes (the cave reloads them on every entry)
    _vr_known = lazy(set)         # Victory Road: remembered boulder tiles (the game only reports objects near the camera)
    _vr_epoch = -1                # reader.map_epoch when _vr_known was last valid: any map change since means the floor was reloaded (boulders reset), so the memory is stale
    _sf_floor = None              # Seafoam B3F: the floor whose boulders _sf_known describes (the cave reloads them on every entry)
    _sf_known = lazy(set)         # Seafoam B3F: remembered boulder tiles

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
