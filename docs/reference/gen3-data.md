# Gen III data structures

How Agent Indigo reads a Pokémon out of the emulator's memory (implemented in `game/memory_reader.py` and `game/constants.py`).

## Party structs and decryption

### Why This Matters

Party Pokémon data is partially XOR-encrypted. **Species ID and moves require decryption.** HP, level, and status are stored unencrypted and always readable. Getting this wrong means silently reading garbage for species and moves.

### 100-Byte Party Structure Layout

Each of the 6 party slots is 100 bytes at `PARTY_DATA + (slot * 100)`.

| Offset | Size | Field | Encrypted? |
|--------|------|-------|-----------|
| `0x00` | 4 | Personality value (PID) | No |
| `0x04` | 4 | OT ID (public + secret) | No |
| `0x08` | 10 | Nickname (Gen III charset) | No |
| `0x12` | 1 | Language | No |
| `0x13` | 1 | Misc flags | No |
| `0x14` | 7 | OT name | No |
| `0x1B` | 1 | Markings | No |
| `0x1C` | 2 | Checksum | No |
| `0x1E` | 2 | Padding | No |
| **`0x20`** | **48** | **Substructures (G/A/E/M) — XOR encrypted** | **Yes** |
| `0x50` | 4 | Status condition bitmask | **No** |
| `0x54` | 1 | Level | **No** |
| `0x55` | 1 | Mail ID | No |
| `0x56` | 2 | Current HP | **No** |
| `0x58` | 2 | Max HP | **No** |
| `0x5A`–`0x62` | 14 | Battle stats (Atk/Def/Spd/SpA/SpD) | No |

**Tier 1 (no decryption needed):** Level, HP, Max HP, Status — get the agent running with just these.
**Tier 2 (decryption):** Species ID and moves — add after Tier 1 is working.

### XOR Decryption

```python
SUBSTRUCT_ORDER = [
    "GAEM", "GAME", "GEAM", "GEMA", "GMAE", "GMEA",
    "AGEM", "AGME", "AEGM", "AEMG", "AMGE", "AMEG",
    "EGAM", "EGMA", "EAGM", "EAMG", "EMGA", "EMAG",
    "MGAE", "MGEA", "MAGE", "MAEG", "MEGA", "MEAG",
]

def decrypt_substructs(raw_100: bytes) -> dict[str, bytes]:
    pid   = int.from_bytes(raw_100[0:4], "little")
    ot_id = int.from_bytes(raw_100[4:8], "little")
    key   = pid ^ ot_id
    enc   = bytearray(raw_100[32:80])
    for i in range(0, 48, 4):
        word = int.from_bytes(enc[i:i+4], "little") ^ key
        enc[i:i+4] = word.to_bytes(4, "little")
    order = SUBSTRUCT_ORDER[pid % 24]
    return {letter: bytes(enc[i * 12:(i + 1) * 12]) for i, letter in enumerate(order)}

def parse_species(sub: dict[str, bytes]) -> int:
    return int.from_bytes(sub["G"][0:2], "little")

def parse_moves(sub: dict[str, bytes]) -> tuple[list[int], list[int]]:
    a = sub["A"]
    return [int.from_bytes(a[i*2:(i+1)*2], "little") for i in range(4)], [a[8+i] for i in range(4)]

def decode_status(word: int) -> str:
    if word == 0: return "healthy"
    sleep = word & 0b111
    if sleep: return f"asleep ({sleep} turns)"
    if word & (1 << 3): return "poisoned"
    if word & (1 << 4): return "burned"
    if word & (1 << 5): return "frozen"
    if word & (1 << 6): return "paralyzed"
    if word & (1 << 7): return "badly_poisoned"
    return "unknown"
```

### Attacks Substructure (A, 12 bytes post-decrypt)

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 2 | Move 1 ID |
| 0x02 | 2 | Move 2 ID |
| 0x04 | 2 | Move 3 ID |
| 0x06 | 2 | Move 4 ID |
| 0x08 | 1 | PP move 1 |
| 0x09 | 1 | PP move 2 |
| 0x0A | 1 | PP move 3 |
| 0x0B | 1 | PP move 4 |

### Growth Substructure (G, 12 bytes post-decrypt)

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 2 | Species ID (National Dex) |
| 0x02 | 2 | Held item ID |
| 0x04 | 4 | Experience |
| 0x08 | 1 | PP bonuses |
| 0x09 | 1 | Friendship |

### Gen III Character Table (for Nickname/Name decoding)

```python
GEN3_CHARSET: dict[int, str | None] = {
    0x00: " ",
    0xA1: "0", 0xA2: "1", 0xA3: "2", 0xA4: "3", 0xA5: "4",
    0xA6: "5", 0xA7: "6", 0xA8: "7", 0xA9: "8", 0xAA: "9",
    0xAB: "!", 0xAC: "?", 0xAD: ".", 0xAE: "-", 0xAF: "…",
    0xBB: "A", 0xBC: "B", 0xBD: "C", 0xBE: "D", 0xBF: "E",
    0xC0: "F", 0xC1: "G", 0xC2: "H", 0xC3: "I", 0xC4: "J",
    0xC5: "K", 0xC6: "L", 0xC7: "M", 0xC8: "N", 0xC9: "O",
    0xCA: "P", 0xCB: "Q", 0xCC: "R", 0xCD: "S", 0xCE: "T",
    0xCF: "U", 0xD0: "V", 0xD1: "W", 0xD2: "X", 0xD3: "Y",
    0xD4: "Z",
    0xD5: "a", 0xD6: "b", 0xD7: "c", 0xD8: "d", 0xD9: "e",
    0xDA: "f", 0xDB: "g", 0xDC: "h", 0xDD: "i", 0xDE: "j",
    0xDF: "k", 0xE0: "l", 0xE1: "m", 0xE2: "n", 0xE3: "o",
    0xE4: "p", 0xE5: "q", 0xE6: "r", 0xE7: "s", 0xE8: "t",
    0xE9: "u", 0xEA: "v", 0xEB: "w", 0xEC: "x", 0xED: "y",
    0xEE: "z",
    0xFC: "\n", 0xFD: "[NAME]", 0xFE: "\n\n", 0xFF: None,
}

def decode_gen3_string(raw: bytes) -> str:
    chars = []
    for byte in raw:
        ch = GEN3_CHARSET.get(byte)
        if ch is None:
            break
        chars.append(ch)
    return "".join(chars)
```

---

## Dialog observation — state diffing

The agent doesn't read dialog text character-by-character. It detects **what changed** between two state polls. Every meaningful game event leaves a detectable footprint:

| Game Event | How Detected |
|-----------|-------------|
| Took damage | Party HP decreased |
| Leveled up | Party level increased |
| Learned move | Party moves changed (Tier 2) |
| Caught Pokémon | Party count increased |
| Earned badge | Badge bitmask changed |
| Battle ended | context left `IN_BATTLE` (`gMain.callback2` no longer the battle callback) |
| Healed | All HP values restored to max |

For dialog that just needs advancing (NPC text, item fanfares): press A until context changes. The **stuck detector** in `ShortTermMemory` fires when the same action repeats 5+ times with no state change, switching the agent to dialog-advance mode automatically.
