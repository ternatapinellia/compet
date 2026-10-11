# CompetSoundFix.py
# ---------------------------------------------------------------------------
# Runtime patch for the Compet desktop pet:
#   1. Rotate numbered sound families (spam_01..spam_10) instead of replaying a
#      single sample.
#   2. Wait for QSoundEffect to reach Ready before play(), because setSource()
#      loads asynchronously and the original code drops the call while loading.
#
# The DLL injects this script very early in startup, when the frozen app's
# module system is not ready yet.  install() is therefore retried from a
# background thread until the imports succeed.
#
# Nothing on disk is modified; restarting Compet reverts everything.
# ---------------------------------------------------------------------------

import os
import re
import sys
import time
import threading

POOL_RE = re.compile(r"^(.*?)(\d+)$")


def _pool_key(path):
    """'spam_01.wav' -> ('spam_', '01');  None when the stem has no number."""
    stem = os.path.splitext(os.path.basename(path))[0]
    m = POOL_RE.match(stem)
    return (m.group(1), m.group(2)) if m else None


def _collect_pool(chosen_path, user_dir, bundle_dir):
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
    return out or [chosen_path]


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

    def _fill_pool(pool, paths):
        if not paths:
            for p in pool:
                try:
                    p.setSource(QUrl())
                except Exception:
                    pass
            return
        for i, player in enumerate(pool):
            try:
                player.setSource(QUrl.fromLocalFile(paths[i % len(paths)]))
            except Exception:
                pass

    def _ready(player):
        try:
            return player.status() == QSoundEffect.Status.Ready
        except Exception:
            return True

    def _play_now(player):
        """Play once the sample finished loading; the naive call is dropped."""
        if _ready(player):
            try:
                player.play()
            except Exception:
                pass
            return

        holder = {"done": False}

        def on_change():
            if holder["done"]:
                return
            if _ready(player):
                holder["done"] = True
                try:
                    player.statusChanged.disconnect(on_change)
                except Exception:
                    pass
                try:
                    player.play()
                except Exception:
                    pass

        try:
            player.statusChanged.connect(on_change)
        except Exception:
            try:
                player.play()
            except Exception:
                pass

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

        self._key_pool_paths = _collect_pool(k_path, user_dir, sound_dir)
        self._click_pool_paths = _collect_pool(c_path, user_dir, sound_dir)

        _fill_pool(self.key_pool, self._key_pool_paths)
        _fill_pool(self.click_pool, self._click_pool_paths)
        self.update_volumes()

    def play_key(self):
        if not self._initialized or not self.key_pool:
            return
        if not _sound_flag(config_mgr, "key_sound_enabled", True):
            return
        player = self.key_pool[self.key_idx]
        self.key_idx = (self.key_idx + 1) % len(self.key_pool)
        _play_now(player)

    def play_click(self):
        if not self._initialized or not self.click_pool:
            return
        if not _sound_flag(config_mgr, "click_sound_enabled", True):
            return
        player = self.click_pool[self.click_idx]
        self.click_idx = (self.click_idx + 1) % len(self.click_pool)
        _play_now(player)

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
    for _ in range(120):            # ~60 s
        try:
            if install():
                import core.sound_manager as sm
                n = len(getattr(getattr(sm, "sound_mgr", None), "_key_pool_paths", []) or [])
                _log("sound fix installed (key pool = %d files)" % n)
                return
        except Exception as e:
            last = e
        time.sleep(0.5)
    _log("sound fix FAILED after retries: %r" % (last,))


LOG_PATH = os.path.join(os.path.expanduser("~"), "_compet_sound_fix.log")


def _log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


threading.Thread(target=_worker, daemon=True).start()
