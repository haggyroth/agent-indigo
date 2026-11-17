"""ShortTermMemory tracks position (0,0) like any other tile (#20)."""
from memory.short_term import ShortTermMemory


def test_origin_is_tracked_not_treated_as_unknown():
    stm = ShortTermMemory()
    # Standing still at the map origin (0,0). The first call establishes the
    # position; each subsequent no-move increments steps_without_movement, so
    # 5 calls -> 4 no-move steps -> stuck. (0,0) must be a real coordinate.
    for _ in range(5):
        stm.record_action("press:Up", 0, 0)
    assert stm.steps_without_movement == 4
    assert stm.stuck is True
    assert stm.visit_count(0, 0) == 5


def test_movement_resets_stuck():
    stm = ShortTermMemory()
    stm.record_action("press:Up", 0, 0)  # establishes position
    stm.record_action("press:Up", 0, 0)  # no move -> 1
    stm.record_action("press:Up", 0, 0)  # no move -> 2
    assert stm.steps_without_movement == 2
    stm.record_action("press:Up", 0, 1)  # actually moved
    assert stm.steps_without_movement == 0
    assert not stm.stuck


def test_unknown_position_does_not_touch_movement():
    stm = ShortTermMemory()
    stm.record_action("press:Up", 5, 5)  # establishes position
    stm.record_action("press:Up", 5, 5)  # no move -> 1
    stm.record_action("press:Up", 5, 5)  # no move -> 2
    assert stm.steps_without_movement == 2
    # A position-less record (e.g. reasoning-only) must not change movement state.
    stm.record_action("thinking...")
    assert stm.steps_without_movement == 2


def test_same_action_at_a_new_position_is_not_stuck_and_history_is_capped():
    stm = ShortTermMemory()
    for i in range(40):
        stm.record_action("press:Right", i, 0)
    assert stm.steps_without_movement == 0 and not stm.stuck
    assert len(stm.action_history) == 30 and stm.action_history[-1] == "press:Right"
    assert stm.visit_count(39, 0) == 1 and stm.visit_count(99, 99) == 0


def test_new_map_clears_visits_and_the_stuck_counter_but_keeps_history():
    stm = ShortTermMemory()
    for _ in range(5):
        stm.record_action("press:Up", 2, 2)
    assert stm.stuck and stm.visit_count(2, 2) == 5
    stm.reset_for_new_map()
    assert not stm.stuck and stm.visit_count(2, 2) == 0 and len(stm.action_history) == 5


def test_new_battle_clears_the_stuck_counter():
    stm = ShortTermMemory()
    for _ in range(5):
        stm.record_action("press:A", 1, 1)
    assert stm.stuck
    stm.reset_for_new_battle()
    assert stm.steps_without_movement == 0
