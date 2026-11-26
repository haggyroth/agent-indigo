"""In-process mGBA emulator client.

Drives libmgba directly via the compiled `game._mgba_native` binding: no mGBA
GUI, no Lua socket, no HTTP round-trips. The emulator only advances when we run
frames, so button presses and `tick()` explicitly step it.

Build the binding first if needed:  python -m game._mgba_build
"""
import os
import zlib
from pathlib import Path
from config import ROM_PATH, SAVE_DIR, SHOW_WINDOW

try:
    from game._mgba_native import ffi, lib
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "game._mgba_native is not built. Run:  python -m game._mgba_build\n"
        "(requires Homebrew libmgba:  brew install mgba)"
    ) from e

# GBA key bit positions (from libmgba's enum GBAKey).
_KEY_BIT = {
    "A": 0, "B": 1, "Select": 2, "Start": 3, "Right": 4,
    "Left": 5, "Up": 6, "Down": 7, "R": 8, "L": 9,
}

# Frame timing. A tap holds then releases; movement needs the button held long
# enough for the walk animation to commit a tile.
TAP_HOLD_FRAMES = 8
TAP_RELEASE_FRAMES = 8
# A running step (B held with the direction): a tile takes 8 frames instead of 16. Held for under one step, so the key is up at the tile boundary and no second step starts
# (measured: 10 presses = 10 tiles, 100 frames against 180).
RUN_HOLD_FRAMES = 4
RUN_RELEASE_FRAMES = 4
IDLE_TICK_FRAMES = 6  # advanced by main loop each iteration (animations/fades)


def _mask(buttons) -> int:
    m = 0
    for b in buttons:
        if b not in _KEY_BIT:
            raise ValueError(f"invalid button {b!r}; valid: {list(_KEY_BIT)}")
        m |= 1 << _KEY_BIT[b]
    return m


class NativeMGBAClient:
    def __init__(self, rom_path: str | None = None, show_window: bool | None = None):
        rom = str(rom_path or ROM_PATH)
        if not Path(rom).is_file():
            raise FileNotFoundError(f"ROM not found: {rom}")
        self._h = lib.pycore_load(rom.encode())
        if self._h == ffi.NULL:
            raise RuntimeError(f"libmgba failed to load ROM: {rom}")
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        self._session_saves: dict[int, int] = {}      # slot -> save order, for slots written by THIS process (see saved_this_session)
        self._save_seq = 0

        # Live framebuffer view + optional window.
        w = ffi.new("uint32_t*"); h = ffi.new("uint32_t*")
        lib.pycore_video_dims(self._h, w, h)
        self._vw, self._vh = int(w[0]), int(h[0])
        self._video = ffi.cast("uint8_t*", lib.pycore_video_ptr(self._h))
        self._video_bytes = self._vw * self._vh * 4  # RGBX
        self._viewer = None
        if SHOW_WINDOW if show_window is None else show_window:
            from game.viewer import PygameViewer
            self._viewer = PygameViewer(self._vw, self._vh)

    def flush_viewer(self) -> None:
        """Show the newest emulated frame in the window (the viewer only presents ~60×/s while frames fly by)."""
        v = self._viewer
        if v is not None:
            v.flush(ffi.buffer(self._video, self._video_bytes))

    def framebuffer(self) -> bytes:
        """Latest frame as RGBX bytes (width*height*4)."""
        if self._h in (None, ffi.NULL):
            raise RuntimeError("the emulator is closed")           # the frame buffer was freed with the core
        return bytes(ffi.buffer(self._video, self._video_bytes))

    def framebuffer_png(self) -> bytes:
        """The latest frame as a PNG, encoded in memory (RGB, no disk round-trip — nothing stale to read back if a write fails)."""
        fb, w, h = self.framebuffer(), self._vw, self._vh
        rows = bytearray()
        row = bytearray(w * 3)
        for y in range(h):
            px = fb[y * w * 4:(y + 1) * w * 4]                         # [R, G, B, pad] per pixel
            row[0::3], row[1::3], row[2::3] = px[0::4], px[1::4], px[2::4]
            rows += b"\x00" + row                                     # filter type 0 (none)

        def chunk(tag: bytes, data: bytes) -> bytes:
            body = tag + data
            return len(data).to_bytes(4, "big") + body + zlib.crc32(body).to_bytes(4, "big")
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", w.to_bytes(4, "big") + h.to_bytes(4, "big") + bytes([8, 2, 0, 0, 0]))
                + chunk(b"IDAT", zlib.compress(bytes(rows), 1)) + chunk(b"IEND", b""))

    # ── Frame stepping ───────────────────────────────────────────────────────

    # A FrameWatchdog (game/watchdog.py) armed around one tool call; None outside skills.
    watchdog = None

    def set_watchdog(self, wd) -> None:
        self.watchdog = wd

    def run_frames(self, n: int) -> None:
        wd = self.watchdog
        if wd is not None:
            wd.advance(n)
        v = self._viewer
        if v is None:
            for _ in range(n):
                lib.pycore_run_frame(self._h)
        else:
            for _ in range(n):
                lib.pycore_run_frame(self._h)
                v.render(ffi.buffer(self._video, self._video_bytes))

    def tick(self, frames: int = IDLE_TICK_FRAMES) -> None:
        """Advance the emulator with no input (animations, fades, NPC motion)."""
        lib.pycore_set_keys(self._h, 0)
        self.run_frames(frames)

    def wait_until_idle(self, max_frames: int = 300, stable: int = 8) -> bool:
        """Run frames (no input) until the screen stops changing — i.e. the game
        is waiting for input (a text box finished printing, or a menu is up).

        Battle text/menus only accept input once idle; pressing during printing or
        animation is silently dropped (the root cause of the in-battle flailing).
        Returns True if idle was reached, False on timeout. Native backend only.
        """
        lib.pycore_set_keys(self._h, 0)
        last = None
        streak = 0
        v = self._viewer
        wd = self.watchdog
        for i in range(max_frames):
            if wd is not None and i % 30 == 0:
                wd.advance(30)
            lib.pycore_run_frame(self._h)
            buf = ffi.buffer(self._video, self._video_bytes)
            if v is not None:
                v.render(buf)
            # Deliberately a SPARSE fingerprint (and not the whole frame): in battle the Pokémon sprites bob and the HP bars tick even while the game is waiting
            # for input, so a whole-frame hash is never "idle" there. The sample ignores those small animations and sees the screen-wide changes (text printing,
            # menu transitions). Tried the whole frame in #381: three live battle tests (Ether, the status-spam watchdog, Victory Road) regressed.
            h = hash(tuple(buf[i] for i in range(0, self._video_bytes, 311)))
            streak = streak + 1 if h == last else 0
            last = h
            if streak >= stable:
                return True
        return False

    def reset(self) -> None:
        """Reboot the core (as if power-cycled). Battery save data persists."""
        lib.pycore_reset(self._h)

    def load_save(self, path: str) -> bool:
        """Load a battery save file (.sav) into the cartridge's save memory.

        Call before reset() so the title screen offers "Continue":
            m.load_save("game.sav"); m.reset()
        Returns True on success. This is the cartridge save, not a save state.
        """
        return bool(lib.pycore_load_save(self._h, str(path).encode()))

    # ── Buttons ──────────────────────────────────────────────────────────────

    def _press(self, mask: int) -> None:
        lib.pycore_set_keys(self._h, mask)
        try:
            self.run_frames(TAP_HOLD_FRAMES)
        finally:
            lib.pycore_set_keys(self._h, 0)         # a watchdog trip inside run_frames must not leave the key held
        self.run_frames(TAP_RELEASE_FRAMES)

    def tap(self, button: str) -> None:
        self._press(_mask([button]))

    def run_step(self, button: str) -> None:
        """One step with the Running Shoes (B held with the direction): half the frames of tap()."""
        lib.pycore_set_keys(self._h, _mask([button, "B"]))
        try:
            self.run_frames(RUN_HOLD_FRAMES)
        finally:
            lib.pycore_set_keys(self._h, 0)
        self.run_frames(RUN_RELEASE_FRAMES)

    def hold(self, button: str, duration_frames: int) -> None:
        lib.pycore_set_keys(self._h, _mask([button]))
        try:
            self.run_frames(max(1, duration_frames))
        finally:
            lib.pycore_set_keys(self._h, 0)
        self.run_frames(2)

    # ── Memory reads ─────────────────────────────────────────────────────────

    def read8(self, address: int) -> int:
        return int(lib.pycore_read8(self._h, address)) & 0xFF

    def read16(self, address: int) -> int:
        return int(lib.pycore_read16(self._h, address)) & 0xFFFF

    def read32(self, address: int) -> int:
        return int(lib.pycore_read32(self._h, address)) & 0xFFFFFFFF

    MAX_READ = 1 << 20      # 1 MiB: far above anything the agent reads (a box blob is 33 KB); a bad length must not allocate / loop up to 4 GiB

    def read_range(self, address: int, length: int) -> bytes:
        if not 0 <= length <= self.MAX_READ:
            raise ValueError(f"read_range length {length} outside 0..{self.MAX_READ}")
        buf = ffi.new("uint8_t[]", length)
        lib.pycore_read_range(self._h, address, length, buf)
        return bytes(buf)

    # ── Memory writes ────────────────────────────────────────────────────────

    def write8(self, address: int, value: int) -> None:
        lib.pycore_write8(self._h, address, value & 0xFF)

    def write16(self, address: int, value: int) -> None:
        lib.pycore_write16(self._h, address, value & 0xFFFF)

    def write32(self, address: int, value: int) -> None:
        lib.pycore_write32(self._h, address, value & 0xFFFFFFFF)

    # ── State management ─────────────────────────────────────────────────────

    def _slot_path(self, slot: int) -> str:
        return str(SAVE_DIR / f"slot_{slot}.ss1")

    def _save_atomic(self, path: str) -> bool:
        """Write the state beside its target and rename it into place: a failure (or a crash) mid-write leaves the previous file, never a truncated one."""
        tmp = f"{path}.tmp"
        try:
            ok = bool(lib.pycore_save_state(self._h, tmp.encode()))
            if ok:
                os.replace(tmp, path)
            return ok
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def save_state(self, slot: int = 0) -> bool:
        """Save to a numbered slot. Returns True on success (False if the core
        rejected it), so callers don't silently believe a failed save."""
        ok = self._save_atomic(self._slot_path(slot))
        if ok:
            self._save_seq += 1
            self._session_saves[int(slot)] = self._save_seq
        return ok

    def saved_this_session(self, slot: int) -> bool:
        """Was `slot` written by this process? Slot files live in saves/ across runs, so a file that merely EXISTS can be months
        old (a title-screen state from July): loading it 'recovered' a blackout by resetting the game to its new-game intro."""
        return int(slot) in self._session_saves

    def load_state(self, slot: int = 0) -> bool:
        """Load from a numbered slot. Returns False if the slot file is missing
        or the core rejected it — callers must handle a failed load (e.g. no state
        was saved yet this session) rather than assuming a reload happened."""
        return bool(lib.pycore_load_state(self._h, self._slot_path(slot).encode()))

    def save_state_file(self, path: str) -> bool:
        return self._save_atomic(str(path))

    def load_state_file(self, path: str) -> bool:
        return bool(lib.pycore_load_state(self._h, str(path).encode()))

    # ── Info / verification ──────────────────────────────────────────────────

    def get_game_title(self) -> str:
        # ROM header title: 12 bytes at bus 0x080000A0.
        raw = self.read_range(0x080000A0, 12)
        return raw.split(b"\x00")[0].decode("ascii", "replace").strip()

    def get_game_code(self) -> str:
        # ROM header game code: 4 bytes at bus 0x080000AC (e.g. "BPGE").
        code = self.read_range(0x080000AC, 4).decode("ascii", "replace")
        return f"AGB-{code}"

    def screenshot(self, path: str) -> bool:
        """Write the frame as a PNG at `path`. False when the core could not (the file is then NOT trusted: a caller must not read back a previous image)."""
        ok = bool(lib.pycore_screenshot(self._h, str(path).encode()))
        if not ok:
            try:
                os.unlink(str(path))                    # whatever partial / stale file is there
            except OSError:
                pass
        return ok

    def log(self, message: str) -> None:
        print(f"[mgba] {message}")

    def verify_connection(self) -> bool:
        try:
            return "BPGE" in self.get_game_code()
        except Exception:
            return False

    def close(self) -> None:
        """Release the viewer and the core now (idempotent). The frame buffer is freed with the core, so framebuffer() raises afterwards instead of reading freed memory."""
        try:
            if getattr(self, "_viewer", None) is not None:
                self._viewer.close()
                self._viewer = None
        except Exception:
            pass
        try:
            if getattr(self, "_h", None) not in (None, ffi.NULL):
                lib.pycore_destroy(self._h)
        except Exception:
            pass
        self._h = None
        self._video = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        self.close()
