"""quest('flash') before Cut: name the one beat to run first, not the next link of a four-step chain (a watched run called it eight times). No emulator."""
from knowledge import story_beats as sb


def status(**over):
    st = {b.key: "done" for b in sb.BEATS}                            # everything earlier in the story is done
    st.update(over)
    return st


def test_first_open_follows_the_needs_to_the_beat_that_can_run_now():
    s = status(misty="next", ss_ticket="blocked", cut="blocked", surge="blocked", flash="blocked")
    assert sb.first_open("flash", s).key == "misty"                              # flash <- surge <- cut <- ss_ticket <- misty
    s = status(cut="next", surge="blocked", flash="blocked")
    assert sb.first_open("flash", s).key == "cut"
    s = status(flash="next")
    assert sb.first_open("flash", s).key == "flash"                              # nothing earlier is missing: flash itself
    assert sb.first_open("flash", status(flash="done")) is None


def test_quest_flash_without_cut_names_the_chain_and_what_to_run_first():
    import pytest
    pytest.importorskip("openai")
    from types import SimpleNamespace as NS
    from agent.lm_studio_client import AgentClient
    from game.state import GameContext
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_flag=lambda f: False, detect_context=lambda: GameContext.OVERWORLD, read_pokedex=lambda: (99, 99))
    c._can_use_cut = lambda: False
    c._story = lambda: status(cut="next", surge="blocked", flash="blocked")
    c._gift_errand = lambda *a, **k: pytest.fail("must not walk to the east building without Cut")
    out = c._get_flash()
    assert out.startswith("Not yet") and "misty → ss_ticket → cut → surge → flash" in out and "quest('cut')" in out and "Don't call quest('flash') again" in out, out
    c._story = lambda: status(flash="next")                                       # chain complete but nobody knows Cut yet
    assert "teach_move('Cut')" in c._get_flash()
