"""Hardware-free tests for game.naming.NamingDriver against a fake that models the Gen III
naming screen (cursor wrap, button column, page cycle UPPER->lower->SYMBOLS, START->OK)."""
from game.constants import GEN3_CHARSET, Addr
from game.naming import _COLS, _PAGES, LOWER, SYMBOLS, UPPER, NamingDriver, key_pos, typeable

_ENC = {v: k for k, v in GEN3_CHARSET.items() if v and len(v) == 1}
_ROWS = {UPPER: 4, LOWER: 4, SYMBOLS: 4}


class FakeNaming:
    def __init__(self, drop_every=0):
        self.page, self.x, self.y = UPPER, 0, 0
        self.buf = []
        self.open = True
        self.btn_y = 0
        self.presses = 0
        self.drop_every = drop_every      # drop every Nth D-pad press (tests self-correction)

    # emulator surface
    def read32(self, a):
        return Addr.NAMING_CB2 if (a == Addr.GMAIN_CALLBACK2 and self.open) else 0

    def read8(self, a):
        if a == Addr.NAMING_PAGE:
            return {UPPER: 1, LOWER: 2, SYMBOLS: 0}[self.page]            # the game's currentPage numbering
        return 0                                                          # BATTLE_YESNO_CURSOR: YES

    def read16(self, a):
        return {Addr.NAMING_CURSOR_X: self.x, Addr.NAMING_CURSOR_Y: self.y}.get(a, 0)

    def read_range(self, a, n):
        out = [_ENC[c] for c in self.buf] + [0xFF] * n
        return bytes(out[:n])

    def tick(self, n=1):
        pass

    def tap(self, b):
        self.presses += 1
        cols = _COLS[self.page]
        if b in ("Left", "Right", "Up", "Down"):
            if self.drop_every and self.presses % self.drop_every == 0:
                return
            if b in ("Left", "Right"):
                px = self.x
                self.x += 1 if b == "Right" else -1
                if self.x < 0:
                    self.x = cols
                if self.x > cols:
                    self.x = 0
                if self.x == cols:
                    self.btn_y = self.y
                    self.y = {0: 0, 1: 1, 2: 1, 3: 2}[self.y]
                elif px == cols:
                    self.y = self.btn_y if self.y == 1 else {0: 0, 2: 3}[self.y]
            else:
                self.y += 1 if b == "Down" else -1
                lim = 3 if self.x == cols else 4
                self.y %= lim
        elif b == "Select":
            self.page = (self.page + 1) % 3
            self.x = min(self.x, _COLS[self.page])
        elif b == "Start":
            self.x, self.y = cols, 2
        elif b == "B":
            if self.buf:
                self.buf.pop()
        elif b == "A":
            if self.x == cols:
                if self.y == 2:
                    self.open = False
                elif self.y == 0:
                    self.tap("Select")
                elif self.buf:
                    self.buf.pop()
            else:
                rows = _PAGES[self.page]
                if self.y < len(rows) and self.x < len(rows[self.y]) and len(self.buf) < 10:
                    self.buf.append(rows[self.y][self.x])


def test_key_pos_and_typeable():
    assert key_pos("A") == (UPPER, 0, 0)
    assert key_pos("z") == (LOWER, 6, 3)
    assert key_pos("7")[0] == SYMBOLS
    assert typeable("Mr. Zap 1") and not typeable("Pika#")


def test_types_a_mixed_case_name_across_pages():
    f = FakeNaming()
    out = NamingDriver(f).enter_name("Sparky")
    assert out == "Named it 'Sparky'." and not f.open and "".join(f.buf) == "Sparky"


def test_names_with_digits_space_and_punctuation():
    f = FakeNaming()
    assert NamingDriver(f).enter_name("Mr. Zap 1").startswith("Named")
    assert "".join(f.buf) == "Mr. Zap 1"


def test_recovers_from_dropped_dpad_presses():
    f = FakeNaming(drop_every=3)
    assert NamingDriver(f).enter_name("Ash").startswith("Named")
    assert "".join(f.buf) == "Ash"


def test_rejects_untypeable_and_inactive():
    f = FakeNaming()
    assert "Can't type" in NamingDriver(f).enter_name("Bad#Name")
    f.open = False
    assert NamingDriver(f).enter_name("X") == "The naming screen isn't open."


def test_truncates_to_ten():
    f = FakeNaming()
    NamingDriver(f).enter_name("Abcdefghijklmno")
    assert "".join(f.buf) == "Abcdefghij"


def test_the_page_is_read_from_the_game_not_assumed():
    f = FakeNaming()
    f.page = LOWER                                    # the screen is somewhere the driver did not expect
    d = NamingDriver(f)
    assert d.current_page() == LOWER
    assert d.enter_name("Rex").startswith("Named") and "".join(f.buf) == "Rex"


def test_abort_clears_the_box_and_leaves_with_the_default_name():
    f = FakeNaming()
    d = NamingDriver(f)
    for ch in "Hob":
        d.type_char(ch)
    assert f.buf and d.abort() and not f.open and f.buf == []


def test_clear_empties_a_prefilled_box():
    f = FakeNaming()
    f.buf = list("OLD")
    assert NamingDriver(f).clear() and f.buf == []


# ── agent.skills.battle._give_nickname: it never strands the battle on the keyboard ───────────────────────────────────────────────
import pytest  # noqa: E402

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402


class NickGame(FakeNaming):
    """The Yes/No box in front of the naming screen: the keyboard only opens when A is pressed on YES (unless `never_opens`)."""

    def __init__(self, never_opens=False, **kw):
        super().__init__(**kw)
        self.open = False
        self.never_opens = never_opens
        self.asked = False
        self.b_after_prompt = 0

    def tap(self, b):
        if not self.open and not self.asked and b == "A" and not self.never_opens:
            self.asked = True
            self.open = True
            return
        if not self.open and b == "B":
            self.b_after_prompt += 1
            return
        super().tap(b)


def _client(game):
    c = AgentClient.__new__(AgentClient)
    c.mgba = game
    return c


def test_give_nickname_types_the_models_pick():
    g = NickGame()
    out = _client(g)._give_nickname("Zap Daddy", "Pikachu", [])
    assert out == "Named it 'Zap Daddy'." and "".join(g.buf) == "Zap Daddy" and not g.open


def test_give_nickname_falls_back_to_a_pool_name_when_the_pick_cannot_be_typed():
    g = NickGame()
    out = _client(g)._give_nickname("Bad#Name", "Pikachu", [])
    from knowledge.nicknames import POOL
    assert out.startswith("Named it") and "couldn't be typed" in out and not g.open
    assert "".join(g.buf) in POOL


def test_give_nickname_leaves_the_keyboard_even_when_nothing_can_be_typed():
    g = NickGame(drop_every=1)                       # every D-pad press is dropped: only letters on the first key can land
    out = _client(g)._give_nickname("Waffles", "Pikachu", [])
    assert not g.open                                  # never stranded on the naming screen
    assert out.startswith(("Named", "(couldn't type"))


def test_give_nickname_declines_the_prompt_when_the_keyboard_never_opens():
    g = NickGame(never_opens=True)
    out = _client(g)._give_nickname("Hobbes", "Rattata", [])
    assert "never opened" in out and g.b_after_prompt == 1
