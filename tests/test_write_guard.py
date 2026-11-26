"""The agent writes menu cursors and the battle-style option, nothing else — enforced (#375)."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from game import write_guard
from game.constants import Addr
from game.write_guard import WriteNotAllowed, check

SB2 = 0x02025000


def test_the_sanctioned_cursors_are_allowed():
    assert check(Addr.MOVE_CURSOR, 1) == "MOVE_CURSOR"
    assert check(Addr.ACTION_CURSOR, 1) == "ACTION_CURSOR"
    for off in range(4):
        assert check(Addr.SHOP_DATA + Addr.SHOP_ITEMLIST + off, 1) == "SHOP_ITEMLIST_PTR"


def test_the_battle_style_option_is_allowed_only_through_the_live_pointer():
    assert check(SB2 + write_guard.OPTIONS_RANGE[1], 2, SB2) == "OPTIONS_BITFIELD"
    with pytest.raises(WriteNotAllowed):
        check(SB2 + write_guard.OPTIONS_RANGE[1], 2, 0)                  # SaveBlock2 pointer unreadable: no write
    with pytest.raises(WriteNotAllowed):
        check(SB2 + write_guard.OPTIONS_RANGE[1] + 2, 2, SB2)            # the next field is not ours


@pytest.mark.parametrize("what,addr,width", [
    ("party HP", Addr.PARTY_DATA + 0x56, 2),
    ("party exp (a substructure)", Addr.PARTY_DATA + 32, 4),
    ("enemy party", Addr.ENEMY_PARTY, 1),
    ("gBattleMons[0].hp", Addr.BATTLE_MON0_SPECIES + 0x28, 2),
    ("battle type flags", Addr.BATTLE_TYPE_FLAGS, 4),
    ("RNG (gRngValue)", 0x03005D80, 4),
    ("SaveBlock1 pointer", Addr.SAVEBLOCK1_PTR, 4),
    ("a cursor written too wide", Addr.MOVE_CURSOR, 2),
    ("a cursor straddled", Addr.MOVE_CURSOR - 1, 2),
    ("ROM", 0x08000000, 1),
])
def test_everything_else_is_refused(what, addr, width):
    with pytest.raises(WriteNotAllowed):
        check(addr, width, SB2)


# ── the client enforces it ───────────────────────────────────────────────────────────────────────

core = pytest.importorskip("game.mgba_core", exc_type=ImportError)       # needs the compiled binding


def _client(monkeypatch, unrestricted=False):
    written = []
    lib = SimpleNamespace(pycore_read32=lambda h, a: SB2 if a == Addr.SAVEBLOCK2_PTR else 0,
                          pycore_write8=lambda h, a, v: written.append((a, v)),
                          pycore_write16=lambda h, a, v: written.append((a, v)),
                          pycore_write32=lambda h, a, v: written.append((a, v)))
    monkeypatch.setattr(core, "lib", lib)
    c = core.NativeMGBAClient.__new__(core.NativeMGBAClient)
    c._h = None
    c.unrestricted_writes = unrestricted
    return c, written


def test_the_client_refuses_a_write_off_the_list_and_never_reaches_the_core(monkeypatch):
    c, written = _client(monkeypatch)
    c.write8(Addr.MOVE_CURSOR, 2)
    assert written == [(Addr.MOVE_CURSOR, 2)]
    for fn, addr in ((c.write8, Addr.PARTY_DATA), (c.write16, Addr.PARTY_DATA + 0x56), (c.write32, 0x03005D80)):
        with pytest.raises(WriteNotAllowed):
            fn(addr, 1)
    assert written == [(Addr.MOVE_CURSOR, 2)]


def test_staging_code_can_opt_out_explicitly(monkeypatch):
    c, written = _client(monkeypatch, unrestricted=True)
    c.write16(Addr.PARTY_DATA + 0x56, 1)
    assert written == [(Addr.PARTY_DATA + 0x56, 1)]
    assert core.NativeMGBAClient.unrestricted_writes is False                 # the default for every real run


# ── every write site in the source is a registered one ───────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
# (file, first argument as written) — adding a site means adding its range to game/write_guard.py AND a line here.
ALLOWED_SITES = {
    ("agent/skills/battle.py", "Addr.MOVE_CURSOR"),
    ("agent/skills/battle.py", "Addr.ACTION_CURSOR"),
    ("agent/skills/overworld.py", "Addr.SHOP_DATA + Addr.SHOP_ITEMLIST + off"),
    ("game/options.py", "a"),
}


def _write_sites():
    found = set()
    for py in ROOT.rglob("*.py"):
        rel = py.relative_to(ROOT)
        if rel.parts[0] in ("tests", ".venv", "venv", "logs", "saves") or any(p.startswith(".") for p in rel.parts):
            continue
        for n in ast.walk(ast.parse(py.read_text())):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("write8", "write16", "write32") and n.args:
                found.add((rel.as_posix(), ast.unparse(n.args[0])))
    return found


def test_every_write_call_in_the_source_is_a_registered_site():
    found = _write_sites()
    assert found, "the scan found no write calls — it is broken"
    assert found <= ALLOWED_SITES, f"unregistered RAM write sites: {sorted(found - ALLOWED_SITES)} (see game/write_guard.py)"
    assert ALLOWED_SITES <= found, f"stale entries in ALLOWED_SITES: {sorted(ALLOWED_SITES - found)}"
