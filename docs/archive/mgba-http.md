# The retired mGBA-http backend

> Agent Indigo used to drive the emulator over HTTP (mGBA GUI + Lua socket + the mGBA-http .NET server). That backend was removed — the agent now runs libmgba in-process (see [architecture](../architecture.md)). This page is kept only as a historical record of the API and the old client; **nothing here is used by the code.**

## mGBA-http 0.8.2 — API reference

*(RETIRED: the `http` backend and `game/mgba_client.py` were removed; kept as a reference for the memory-layout notes and the old API.)*

**Base URL:** `http://localhost:5000`
**All endpoints verified against swagger.json from the running server.**

### Button Endpoints

| Action | Method | Endpoint | Params |
|--------|--------|----------|--------|
| Tap (press + release) | POST | `/mgba-http/button/tap` | `button=A` |
| Tap multiple simultaneously | POST | `/mgba-http/button/tapmany` | `buttons=A&buttons=B` |
| Hold for N frames | POST | `/mgba-http/button/hold` | `button=A&duration=30` |
| Hold multiple for N frames | POST | `/mgba-http/button/holdmany` | `buttons=A&buttons=B&duration=30` |
| Add (hold down indefinitely) | POST | `/mgba-http/button/add` | `button=A` |
| Clear (release) | POST | `/mgba-http/button/clear` | `button=A` |
| Get button state | GET | `/mgba-http/button/get` | `button=A` → `"0"` or `"1"` |
| Get all active buttons | GET | `/mgba-http/button/getall` | → `"A,B,Start"` |

**Valid button values:** `A` `B` `Select` `Start` `Right` `Left` `Up` `Down` `R` `L`

### Core Memory Endpoints

**Key insight: these use full GBA bus addresses (e.g. `0x02024284`), no domain name needed.**
**All return plain-text strings, not JSON.**

| Action | Method | Endpoint | Params | Returns |
|--------|--------|----------|--------|---------|
| Read 8-bit | GET | `/core/read8` | `address=0x02024284` | `"255"` (decimal string) |
| Read 16-bit | GET | `/core/read16` | `address=0x02024284` | `"65535"` (decimal string) |
| Read 32-bit | GET | `/core/read32` | `address=0x02024284` | `"4294967295"` (decimal string) |
| Read byte range | GET | `/core/readrange` | `address=0x02024284&length=100` | `"d3,00,ea,66,..."` (comma-sep hex, no 0x) |

### Domain-Based Memory Endpoints (Alternative)

Use these if you need domain-relative addressing. Domain names for GBA: `wram`, `cart0`, `bios`, `iwram`.

| Action | Method | Endpoint | Params | Returns |
|--------|--------|----------|--------|---------|
| Read 8-bit | GET | `/memorydomain/read8` | `memoryDomain=wram&address=0x24284` | `"255"` (decimal) |
| Read byte range | GET | `/memorydomain/readrange` | `memoryDomain=wram&address=0x24284&length=100` | `"d3,00,ea,..."` |
| Get domain size | GET | `/memorydomain/size` | `memoryDomain=wram` | `"262144"` |
| Write 8-bit | POST | `/memorydomain/write8` | `memoryDomain=wram&address=0x24284&value=255` | `""` |
| Write 16-bit | POST | `/memorydomain/write16` | `memoryDomain=wram&address=0x24284&value=65535` | `""` |
| Write 32-bit | POST | `/memorydomain/write32` | `memoryDomain=wram&address=0x24284&value=4294967295` | `""` |

**Prefer `/core/read8|16|32|readrange`** — they take full absolute addresses, directly matching all memory map documentation.

### State Management Endpoints

| Action | Method | Endpoint | Params |
|--------|--------|----------|--------|
| Save to slot | POST | `/core/savestateslot` | `slot=0` |
| Load from slot | POST | `/core/loadstateslot` | `slot=0` |
| Save to file | POST | `/core/savestatefile` | `path=/Users/kylec/Projects/pokemon-agent/saves/pre_gym.ss1` |
| Load from file | POST | `/core/loadstatefile` | `path=/Users/kylec/Projects/pokemon-agent/saves/pre_gym.ss1` |
| Save to buffer | POST | `/core/savestatebuffer` | → hex csv string |
| Load from buffer | POST | `/core/loadstatebuffer` | body: `[d3,00,ea,...]` |

**State flags bitmask:** SCREENSHOT=1, SAVEDATA=2, CHEATS=4, RTC=8, METADATA=16. Default save=31 (all), load=29 (excludes screenshot).

### Other Useful Endpoints

| Action | Method | Endpoint | Returns |
|--------|--------|----------|---------|
| Get game title | GET | `/core/getgametitle` | `"POKEMON LEAF"` |
| Get game code | GET | `/core/getgamecode` | `"AGB-BPGE"` (LeafGreen US) |
| Get platform | GET | `/core/platform` | `"0"` (GBA=0, GB=1) |
| Save screenshot | POST | `/core/screenshot` | `path=/tmp/screenshot.png` |
| Read CPU register | GET | `/core/readregister` | `regName=pc` → decimal |
| Load ROM | POST | `/core/loadfile` | `path=...` |

### Console Logging (writes to mGBA-http terminal)

| Action | Method | Endpoint | Params |
|--------|--------|----------|--------|
| Log | POST | `/console/log` | `message=hello` |
| Warn | POST | `/console/warn` | `message=...` |
| Error | POST | `/console/error` | `message=...` |

---

## Python Client — Canonical Implementation

This is the single source of truth for `game/mgba_client.py`. All method signatures here are derived from the swagger and must match it exactly.

```python
# game/mgba_client.py
import requests
import time
from config import MGBA_HTTP_BASE, BUTTON_TAP_DELAY

class MGBAClient:
    def __init__(self, base_url: str = MGBA_HTTP_BASE):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()

    # ── Response parsing ────────────────────────────────────────────────────

    def _hex_csv_to_bytes(self, text: str) -> bytes:
        """Parse 'aa,bb,cc,dd' response from readrange into bytes."""
        text = text.strip()
        if not text:
            return b""
        return bytes(int(h, 16) for h in text.split(","))

    # ── Buttons ─────────────────────────────────────────────────────────────

    def tap(self, button: str) -> None:
        """Press and release. button must be: A B Select Start Right Left Up Down R L"""
        self.session.post(f"{self.base}/mgba-http/button/tap", params={"button": button})
        time.sleep(BUTTON_TAP_DELAY)

    def tap_many(self, buttons: list[str]) -> None:
        self.session.post(f"{self.base}/mgba-http/button/tapmany",
                          params=[("buttons", b) for b in buttons])
        time.sleep(BUTTON_TAP_DELAY)

    def hold(self, button: str, duration_frames: int) -> None:
        """Hold a button for exactly N frames."""
        self.session.post(f"{self.base}/mgba-http/button/hold",
                          params={"button": button, "duration": duration_frames})

    # ── Memory reads (full absolute GBA bus addresses) ──────────────────────

    def read8(self, address: int) -> int:
        """Read unsigned 8-bit value at absolute GBA bus address."""
        r = self.session.get(f"{self.base}/core/read8",
                             params={"address": hex(address)})
        r.raise_for_status()
        return int(r.text.strip())

    def read16(self, address: int) -> int:
        """Read unsigned 16-bit value at absolute GBA bus address."""
        r = self.session.get(f"{self.base}/core/read16",
                             params={"address": hex(address)})
        r.raise_for_status()
        return int(r.text.strip())

    def read32(self, address: int) -> int:
        """Read unsigned 32-bit value at absolute GBA bus address."""
        r = self.session.get(f"{self.base}/core/read32",
                             params={"address": hex(address)})
        r.raise_for_status()
        return int(r.text.strip())

    def read_range(self, address: int, length: int) -> bytes:
        """Read `length` bytes starting at absolute GBA bus address.
        Response is comma-separated hex: 'd3,00,ea,66,...' — parsed to bytes."""
        r = self.session.get(f"{self.base}/core/readrange",
                             params={"address": hex(address), "length": length})
        r.raise_for_status()
        return self._hex_csv_to_bytes(r.text)

    # ── State management ────────────────────────────────────────────────────

    def save_state(self, slot: int = 0) -> None:
        """Save to a numbered slot (mGBA manages the file location)."""
        self.session.post(f"{self.base}/core/savestateslot",
                          params={"slot": str(slot)})

    def load_state(self, slot: int = 0) -> None:
        """Load from a numbered slot."""
        self.session.post(f"{self.base}/core/loadstateslot",
                          params={"slot": str(slot)})

    def save_state_file(self, path: str) -> bool:
        """Save state to a specific file path. Returns True on success."""
        r = self.session.post(f"{self.base}/core/savestatefile",
                              params={"path": path})
        return r.text.strip().lower() == "true"

    def load_state_file(self, path: str) -> bool:
        """Load state from a specific file path. Returns True on success."""
        r = self.session.post(f"{self.base}/core/loadstatefile",
                              params={"path": path})
        return r.text.strip().lower() == "true"

    # ── Info / verification ─────────────────────────────────────────────────

    def get_game_title(self) -> str:
        """Returns e.g. 'POKEMON LEAF' for LeafGreen."""
        return self.session.get(f"{self.base}/core/getgametitle").text.strip()

    def get_game_code(self) -> str:
        """Returns 'AGB-BPGE' for Pokemon LeafGreen English."""
        return self.session.get(f"{self.base}/core/getgamecode").text.strip()

    def screenshot(self, path: str) -> None:
        """Save a PNG screenshot to the given filesystem path."""
        self.session.post(f"{self.base}/core/screenshot", params={"path": path})

    def log(self, message: str) -> None:
        """Print a message to the mGBA-http console (useful for debugging)."""
        self.session.post(f"{self.base}/console/log", params={"message": message})

    def verify_connection(self) -> bool:
        """Returns True if mGBA-http is running and serving LeafGreen.
        Note: get_game_code() returns 'AGB-BPGE', not just 'BPGE' — use 'in'."""
        try:
            return "BPGE" in self.get_game_code()
        except Exception:
            return False
```

---
