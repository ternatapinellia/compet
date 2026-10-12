# CompetSoundFix.py
# ---------------------------------------------------------------------------
# Runtime patch for the Compet desktop pet:
#   1. Rotate numbered sound families (spam_01..spam_10) instead of replaying a
#      single sample.
#   2. Never go permanently silent.
#
# Why this version exists
# -----------------------
# QSoundEffect loads its source asynchronously, and on this machine a player can
# stay in Loading forever: the previous version logged
# "player 0 never reached Ready - rebuilding".  Any design that waits for the
# Ready state before calling play() can therefore drop every keystroke, and once
# every pool slot is stuck the pet is silent until Compet is restarted.
#
# This version plays the Qt sample when it is already loaded (that keeps the
# per-app volume slider meaningful) and otherwise hands the file straight to the
# WinMM PlaySoundW API, which has no loading state to get stuck in.  One of the
# two paths always makes noise, so the pool cannot latch into silence.
#
# It also survives an empty <prefix>_sound_path.  Settings can end up with an
# empty path (seen on 2026-10-12: "key pool = 0 files"), which used to leave the
# pool empty and therefore silent; the configured path is now optional and a
# bundled family is used when it is missing.
#
# The DLL injects this script very early in startup, when the frozen app's
# module system is not ready yet, so install() is retried from a background
# thread until the imports succeed.
#
# Nothing on disk is modified; restarting Compet reverts everything.
# ---------------------------------------------------------------------------

import ctypes
import os
import re
import sys
import time
import threading

POOL_RE = re.compile(r"^(.*?)(\d+)$")

def _log_targets():
    """Log next to the app as well, so a missing/odd HOME cannot hide output."""
    out = [os.path.join(os.path.expanduser("~"), "_compet_sound_fix.log")]
    try:
        exe = getattr(sys, "executable", "") or ""
        if exe:
            out.append(os.path.join(os.path.dirname(os.path.abspath(exe)),
                                    "_compet_sound_fix.log"))
    except Exception:
        pass
    return out


def _log(msg):
    """Append one line to the diagnostic log; never raise."""
    for path in _log_targets():
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass


_log("script loaded")       # proves the injection actually executed

# ---------------------------------------------------------------- WinMM ----
# PlaySoundW is fire-and-forget: no source, no Ready state, no event loop.
_SND_ASYNC = 0x0001
_SND_NODEFAULT = 0x0002
_SND_FILENAME = 0x00020000

_play_sound = None
_native_failed = set()


def _play_wav_native(path):
    """Start one sample through WinMM.  Returns True when it was accepted."""
    global _play_sound
    if not path or not os.path.exists(path):
        return False
    try:
        if _play_sound is None:
            fn = ctypes.WinDLL("winmm.dll").PlaySoundW
            fn.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint]
            fn.restype = ctypes.c_bool
            _play_sound = fn
        flags = _SND_ASYNC | _SND_FILENAME | _SND_NODEFAULT
        return bool(_play_sound(str(path), None, flags))
    except Exception as e:
        if "winmm" not in _native_failed:
            _native_failed.add("winmm")
            _log("WinMM playback unavailable: %r" % (e,))
        return False


def _pool_key(path):
    """'spam_01.wav' -> ('spam_', '01');  None when the stem has no number."""
    stem = os.path.splitext(os.path.basename(path))[0]
    m = POOL_RE.match(stem)
    return (m.group(1), m.group(2)) if m else None


def _family_paths(chosen_path, user_dir, bundle_dir):
    """Every file in the same numbered family; the user folder wins."""
    if not chosen_path:
        return []
    key = _pool_key(chosen_path)
    if key is None:
        return [chosen_path]

    prefix = key[0].lower()
    out, seen = [], set()
    for d in (user_dir, bundle_dir):
        if not d or not os.path.isdir(d):
            continue
        try:
            names = sorted(os.listdir(d))
        except Exception:
            continue
        for f in names:
            if not f.lower().endswith(".wav"):
                continue
            m = POOL_RE.match(os.path.splitext(f)[0])
            if m is None or m.group(1).lower() != prefix:
                continue
            ln = f.lower()
            if ln in seen:
                continue
            seen.add(ln)
            out.append(os.path.abspath(os.path.join(d, f)))
    return out


def _find_default(default_prefix, user_dir, bundle_dir):
    """First bundled file whose name starts with *default_prefix*, if any."""
    if not default_prefix:
        return None
    for d in (user_dir, bundle_dir):
        if not d or not os.path.isdir(d):
            continue
        try:
            names = sorted(os.listdir(d))
        except Exception:
            continue
        for f in names:
            if f.lower().endswith(".wav") and f.lower().startswith(default_prefix):
                return os.path.join(d, f)
    return None


def _collect_pool(chosen_path, user_dir, bundle_dir, default_prefix=None):
    """The configured family, or a bundled one when the path is empty/missing.

    The app persists <prefix>_sound_path and it can arrive empty, which used to
    leave the pool with zero files and therefore no sound at all.  Falling back
    keeps the pet audible no matter what the settings file contains.
    """
    paths = [p for p in _family_paths(chosen_path, user_dir, bundle_dir)
             if p and os.path.exists(p)]
    if paths:
        return paths

    fallback = _find_default(default_prefix, user_dir, bundle_dir)
    if fallback:
        fallback_paths = [p for p in _family_paths(fallback, user_dir, bundle_dir)
                          if p and os.path.exists(p)]
        if fallback_paths:
            _log("no usable sound path (%r) - using %s" % (chosen_path, fallback))
            return fallback_paths
    return []


def _sound_flag(config_mgr, name, default=True):
    """Read a flag from either config layout (flat 'settings', nested 'config')."""
    for holder, key in ((getattr(config_mgr, "settings", None), name),
                        (getattr(config_mgr, "config", None), None)):
        if not isinstance(holder, dict):
            continue
        if key is not None and key in holder:
            return holder.get(key, default)
        snd = holder.get("sound")
        if isinstance(snd, dict) and name in snd:
            return snd.get(name, default)
    return default


def _ensure_path():
    """Make sure the app's own modules are importable."""
    cands = []
    exe = getattr(sys, "executable", "") or ""
    if exe:
        cands.append(os.path.dirname(exe))
        cands.append(os.path.join(os.path.dirname(exe), "_internal"))
    mp = getattr(sys, "_MEIPASS", None)
    if mp:
        cands.append(mp)
    for c in cands:
        if c and c not in sys.path:
            try:
                sys.path.insert(0, c)
            except Exception:
                pass


def install():
    """Patch SoundManager.  Returns True on success, False when not ready yet."""
    _ensure_path()

    import core.config_manager as cm
    import core.sound_manager as sm
    from PyQt6.QtMultimedia import QSoundEffect
    from PyQt6.QtCore import QUrl
    from core.config_manager import config_mgr

    mgr_cls = sm.SoundManager
    if getattr(mgr_cls, "_compet_sound_patched", False):
        return True

    def _ready(player):
        try:
            return player.status() == QSoundEffect.Status.Ready
        except Exception:
            return True

    def _force(player):
        try:
            player.play()
            return True
        except Exception:
            return False

    def _set_source(player, path):
        try:
            player.setSource(QUrl.fromLocalFile(path) if path else QUrl())
        except Exception:
            pass

    def _fill_pool(pool, paths):
        for i, player in enumerate(pool):
            _set_source(player, paths[i % len(paths)] if paths else None)

    def _start(pool, paths, idx, label):
        """Play pool[idx].  Always audible: Qt when loaded, WinMM otherwise."""
        player = pool[idx]
        if _ready(player) and _force(player):
            return
        path = paths[idx % len(paths)] if paths else None
        if not _play_wav_native(path):
            _force(player)          # last resort; may still be a no-op

    def load_sounds(self):
        if not self._initialized:
            return

        k_path = self.get_actual_path("key")
        c_path = self.get_actual_path("click")

        # This build keeps user sounds under the app's assets folder.
        # Prefer the module's own constant, then the config manager's.
        sound_dir = getattr(sm, "ASSETS_DIR", None) or getattr(cm, "ASSETS_DIR", None)
        user_dir = getattr(cm, "USER_DATA_DIR", None)
        if user_dir:
            user_dir = os.path.join(user_dir, "sounds")

        self._key_pool_paths = _collect_pool(k_path, user_dir, sound_dir, "spam_")
        self._click_pool_paths = _collect_pool(c_path, user_dir, sound_dir, "keyboard")

        _fill_pool(self.key_pool, self._key_pool_paths)
        _fill_pool(self.click_pool, self._click_pool_paths)
        self.update_volumes()

    def play_key(self):
        if not self._initialized or not self.key_pool:
            return
        if not _sound_flag(config_mgr, "key_sound_enabled", True):
            return
        idx = self.key_idx
        self.key_idx = (idx + 1) % len(self.key_pool)
        _start(self.key_pool, getattr(self, "_key_pool_paths", []), idx, "key")

    def play_click(self):
        if not self._initialized or not self.click_pool:
            return
        if not _sound_flag(config_mgr, "click_sound_enabled", True):
            return
        idx = self.click_idx
        self.click_idx = (idx + 1) % len(self.click_pool)
        _start(self.click_pool, getattr(self, "_click_pool_paths", []), idx, "click")

    mgr_cls.load_sounds = load_sounds
    mgr_cls.play_key = play_key
    mgr_cls.play_click = play_click
    mgr_cls._compet_sound_patched = True

    try:
        if getattr(sm.sound_mgr, "_initialized", False):
            sm.sound_mgr.load_sounds()
    except Exception:
        pass
    return True


def _worker():
    """Retry until the app finished starting up and the imports work."""
    last = None
    told = False
    for _ in range(120):            # ~60 s
        try:
            if install():
                import core.sound_manager as sm
                n = len(getattr(getattr(sm, "sound_mgr", None), "_key_pool_paths", []) or [])
                _log("sound fix installed (key pool = %d files)" % n)
                return
        except Exception as e:
            last = e
            if not told:
                told = True
                _log("install not ready yet: %r" % (e,))
        time.sleep(0.5)
    _log("sound fix FAILED after retries: %r" % (last,))


threading.Thread(target=_worker, daemon=True).start()
