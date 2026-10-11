# CompetSoundFix.py
# ---------------------------------------------------------------------------
# Runtime patch for the Compet desktop pet:
#   1. Rotate numbered sound families (spam_01..spam_10) instead of replaying a
#      single sample.
#   2. Make playback survive QSoundEffect's asynchronous loading.
#
# Why this version exists
# -----------------------
# The first version waited for a sample to reach Ready by connecting a throwaway
# handler to QSoundEffect.statusChanged.  When a player never became Ready
# (a half-loaded source, which happens when a new source is set while the old
# one is still loading) that handler stayed connected forever and play() was
# never called again: the pool went permanently silent until Compet restarted.
#
# This version instead
#   * never leaves a dangling statusChanged connection,
#   * retries on a short owned QTimer and gives up cleanly,
#   * rebuilds an individual player that stays unhealthy, so one bad player can
#     no longer mute the whole pool.
#
# The DLL injects this script very early in startup, when the frozen app's
# module system is not ready yet, so install() is retried from a background
# thread until the imports succeed.
#
# Nothing on disk is modified; restarting Compet reverts everything.
# ---------------------------------------------------------------------------

import os
import re
import sys
import time
import threading

POOL_RE = re.compile(r"^(.*?)(\d+)$")

_RETRY_MS = 40           # retry cadence while a sample is still loading
_MAX_RETRIES = 8         # ~320 ms, then the player is treated as unhealthy


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
    from PyQt6.QtCore import QUrl, QTimer
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
        """Play pool[idx], self-healing a player that never becomes Ready."""
        player = pool[idx]

        if _ready(player):
            _force(player)
            return

        # One recovery timer per player: rapid typing must not spawn a burst of
        # timers that each rebuild the same player.
        if getattr(player, "_compet_recovering", False):
            return

        state = {"n": 0}
        timer = QTimer(player)          # parented: dies with the player
        timer.setInterval(_RETRY_MS)
        try:
            player._compet_recovering = True
        except Exception:
            pass

        def tick():
            state["n"] += 1
            if _ready(player):
                timer.stop()
                timer.deleteLater()
                try:
                    player._compet_recovering = False
                except Exception:
                    pass
                _force(player)
                return
            if state["n"] < _MAX_RETRIES:
                return
            try:
                player._compet_recovering = False
            except Exception:
                pass

            # Unhealthy player: rebuild it instead of leaving a half-loaded
            # source (and a dangling signal connection) behind for good.
            timer.stop()
            timer.deleteLater()
            _log("%s: player %d never reached Ready - rebuilding" % (label, idx))
            try:
                fresh = QSoundEffect()
                pool[idx] = fresh
                if paths:
                    _set_source(fresh, paths[idx % len(paths)])
                try:
                    fresh.setVolume(player.volume())
                except Exception:
                    pass
            except Exception:
                pass

        timer.timeout.connect(tick)
        timer.start()

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
