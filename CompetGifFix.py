# CompetGifFix.py
# ---------------------------------------------------------------------------
# Animated (GIF / WebP) skin support for the Compet desktop pet.
#
# How it works
# ------------
# The stock paintEvent() already scales and anchors current_pixmap, so an
# animation only needs that pixmap to change over time.  A QTimer owned by the
# widget swaps the frame and the existing drawing code does the rest.
#
# Why the frames get rescaled
# ---------------------------
# Still skins ship as large images (measured: 570x680 for ggdw / big shot,
# 591x467 for anton, 850x850 for tenna).  A hand-made animation is often much
# smaller (the test GIF is 160x160).  update_widget_size() sizes the window from
# idle_pixmap, and paintEvent() squashes around the centre, so a 160x160 frame
# produced three complaints at once: the pet looked tiny next to the other
# skins, one wheel step changed its size wildly, and the squash/stretch looked
# far too strong for such a small sprite.
#
# Frames are therefore scaled to the skin's own still-image size before use, so
# an animated skin behaves exactly like the PNG skin it replaces.  A skin with
# no still image (animation only) keeps its native size.
#
# Safety
# ------
#   * Skins made of ordinary still images are left completely untouched: every
#     patched method delegates to the original implementation.
#   * Pausing during key presses is deadline-based, so a missed frame cannot
#     freeze the animation forever.
#   * install() is retried from a background thread, because the DLL can run
#     this script before the frozen app's module system is ready.
#   * Nothing on disk is modified; restarting Compet reverts everything.
# ---------------------------------------------------------------------------

import os
import sys
import threading
import time
import traceback

_ANIM_EXTS = (".gif", ".webp")
_STILL_EXTS = (".png", ".jpg", ".jpeg", ".bmp")
_DEFAULT_DELAY_MS = 100
_MIN_DELAY_MS = 20
_MAX_FRAMES = 300            # guard against a runaway animation
_PAUSE_MS = 400              # how long a key press may hold the idle frame


def _log(msg):
    for path in _log_targets():
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(msg + "\n")
        except Exception:
            pass


def _log_targets():
    out = [os.path.join(os.path.expanduser("~"), "_compet_gif_fix.log")]
    try:
        import sys
        exe = getattr(sys, "executable", "") or ""
        if exe:
            out.append(os.path.join(os.path.dirname(os.path.abspath(exe)),
                                    "_compet_gif_fix.log"))
    except Exception:
        pass
    return out


def _error_log(text):
    try:
        with open(os.path.join(os.path.expanduser("~"), "_compet_gif_fix_error.log"),
                  "a", encoding="utf-8") as fh:
            fh.write(text)
    except Exception:
        pass


def _is_anim(path):
    try:
        return str(path).lower().endswith(_ANIM_EXTS)
    except Exception:
        return False


def _read_frames(path):
    """Decode a GIF/WebP into (frames, delays_ms).  None when not animated."""
    from PyQt6.QtGui import QPixmap, QImageReader

    if not (path and os.path.exists(path) and _is_anim(path)):
        return None

    try:
        reader = QImageReader(path)
        if not reader.supportsAnimation():
            return None
        count = reader.imageCount()
        if count <= 1:
            return None
    except Exception:
        return None

    frames, delays = [], []
    try:
        for _ in range(min(count, _MAX_FRAMES)):
            img = reader.read()
            if img.isNull():
                break
            frames.append(QPixmap.fromImage(img))
            d = reader.nextImageDelay()
            delays.append(max(_MIN_DELAY_MS, int(d)) if d and d > 0 else _DEFAULT_DELAY_MS)
    except Exception:
        _error_log(traceback.format_exc())

    if len(frames) < 2:
        return None
    if len(delays) < len(frames):
        delays += [_DEFAULT_DELAY_MS] * (len(frames) - len(delays))
    return frames, delays


def _still_size(skin_dir, anim_name):
    """Size of the skin's still images, used to keep the pet the same size."""
    from PyQt6.QtGui import QImageReader

    try:
        names = sorted(os.listdir(skin_dir))
    except Exception:
        return None
    for name in names:
        if name == anim_name or not name.lower().endswith(_STILL_EXTS):
            continue
        try:
            size = QImageReader(os.path.join(skin_dir, name)).size()
        except Exception:
            continue
        if size.isValid() and size.width() > 0 and size.height() > 0:
            return size
    return None


def _fit_frames(frames, size):
    """Scale every frame to *size* so an animation matches its PNG siblings."""
    from PyQt6.QtCore import Qt

    if size is None or not size.isValid():
        return frames
    if all(f.width() == size.width() and f.height() == size.height() for f in frames):
        return frames
    out = []
    for f in frames:
        try:
            out.append(f.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                Qt.TransformationMode.SmoothTransformation))
        except Exception:
            out.append(f)
    return out


def _loaded_module(name):
    """Fetch an already-imported module without importing it.

    Importing from the retry thread races the application's own startup
    imports (importlib._ModuleLock is keyed by thread id), so only sys.modules
    is consulted here.
    """
    try:
        return sys.modules.get(name)
    except Exception:
        return None


def install():
    """Patch PetWidget.  True when patched, False when not ready yet.

    Every module is taken from sys.modules instead of being imported.  This
    script runs via the DLL on the interpreter's main thread, but its retry
    thread would otherwise import while the application is still starting up;
    the two threads then race importlib's _ModuleLock, which is keyed by thread
    id, and the app dies with `KeyError` from `_bootstrap.acquire`.  A
    sys.modules read is a plain dict lookup and cannot trigger the import
    machinery.
    """
    pw = _loaded_module("ui.pet_widget")
    qtcore = _loaded_module("PyQt6.QtCore")
    if pw is None or qtcore is None:
        return False
    QTimer = getattr(qtcore, "QTimer", None)
    PetWidget = getattr(pw, "PetWidget", None)
    if QTimer is None or PetWidget is None:
        return False
    if getattr(PetWidget, "_compet_gif_patched", False):
        return True

    orig_load = PetWidget.load_resources
    orig_bounce = PetWidget.trigger_bounce
    orig_reset = PetWidget.reset_to_idle

    def _timer(self):
        t = getattr(self, "_compet_gif_timer", None)
        if t is None:
            t = QTimer(self)             # parented: dies together with the pet
            t.setSingleShot(False)
            t.timeout.connect(lambda: _advance(self))
            self._compet_gif_timer = t
        return t

    def _advance(self):
        frames = getattr(self, "_compet_gif_frames", None)
        if not frames:
            return
        # A key press holds the current frame; the deadline means a missed
        # reset can only delay the animation, never freeze it outright.
        if time.time() * 1000.0 < getattr(self, "_compet_gif_pause_until", 0):
            return
        try:
            idx = (getattr(self, "_compet_gif_index", 0) + 1) % len(frames)
            self._compet_gif_index = idx
            self.current_pixmap = frames[idx]
            delays = getattr(self, "_compet_gif_delays", None)
            if delays:
                t = getattr(self, "_compet_gif_timer", None)
                if t is not None:
                    t.setInterval(max(_MIN_DELAY_MS, delays[idx]))
            self.update()
        except Exception:
            _error_log(traceback.format_exc())

    def load_resources(self):
        try:
            orig_load(self)
        except Exception:
            _error_log(traceback.format_exc())

        # --- reset any animation from a previous skin ---------------------
        self._compet_gif_frames = None
        self._compet_gif_delays = None
        self._compet_gif_index = 0
        self._compet_gif_pause_until = 0
        t = getattr(self, "_compet_gif_timer", None)
        if t is not None:
            try:
                t.stop()
            except Exception:
                pass

        try:
            skin = (self.instance_data or {}).get("skin", "default")
            try:
                conf = pw.config_mgr.get_skin_config(skin) or {}
            except Exception:
                conf = {}
            anim_name = conf.get("idle_image", "idle.png")
            if not _is_anim(anim_name):
                return                          # still-image skin: untouched

            skin_dir = os.path.join(pw.SKINS_DIR, skin)
            loaded = _read_frames(os.path.join(skin_dir, anim_name))
            if loaded is None:
                _log("%s: %s is not an animated image - leaving it alone"
                     % (skin, anim_name))
                return

            frames, delays = loaded
            size = _still_size(skin_dir, anim_name)
            frames = _fit_frames(frames, size)

            self._compet_gif_frames = frames
            self._compet_gif_delays = delays
            self._compet_gif_index = 0
            self.current_pixmap = frames[0]

            # Keep the window sized like the PNG skins, otherwise one wheel
            # step would change the scale by a wildly different amount.
            self.idle_pixmap = frames[0]
            try:
                if hasattr(self, "update_widget_size"):
                    self.update_widget_size()
            except Exception:
                _error_log(traceback.format_exc())

            timer = _timer(self)
            timer.setInterval(max(_MIN_DELAY_MS, delays[0]))
            timer.start()
            self.update()
            _log("%s: %s -> %d frames, %dx%d (still size %s)"
                 % (skin, anim_name, len(frames), frames[0].width(),
                    frames[0].height(), size))
        except Exception:
            self._compet_gif_frames = None
            _error_log(traceback.format_exc())

    def trigger_bounce(self, key_payload):
        result = orig_bounce(self, key_payload)
        if getattr(self, "_compet_gif_frames", None):
            # Hold the idle frame while the app shows its own key image.
            self._compet_gif_pause_until = time.time() * 1000.0 + _PAUSE_MS
        return result

    def reset_to_idle(self):
        self._compet_gif_pause_until = 0
        result = orig_reset(self)
        frames = getattr(self, "_compet_gif_frames", None)
        if frames:
            try:
                self.current_pixmap = frames[getattr(self, "_compet_gif_index", 0)]
                self.update()
            except Exception:
                _error_log(traceback.format_exc())
        return result

    PetWidget.load_resources = load_resources
    PetWidget.trigger_bounce = trigger_bounce
    PetWidget.reset_to_idle = reset_to_idle
    PetWidget._compet_gif_patched = True

    # Pets created after this point pick the patch up automatically.  Existing
    # pets are refreshed from the GUI thread via a zero-delay timer: this
    # function can run on the retry thread, and calling load_resources() there
    # would touch Qt widgets off the GUI thread.
    try:
        qtw = _loaded_module("PyQt6.QtWidgets")
        QApplication = getattr(qtw, "QApplication", None)
        if QApplication is not None:
            def _refresh_existing():
                try:
                    for w in QApplication.topLevelWidgets():
                        if isinstance(w, PetWidget):
                            w.load_resources()
                except Exception:
                    _error_log(traceback.format_exc())

            QTimer.singleShot(0, _refresh_existing)
    except Exception:
        _error_log(traceback.format_exc())
    return True


def _worker():
    """The DLL can run us before the frozen app's imports are ready.

    Nothing is imported here: the application is still starting up and an
    import from this thread would race its own imports (see _loaded_module).
    """
    last = None
    told = False
    for _ in range(120):                 # ~60 s
        try:
            exe = getattr(sys, "executable", "") or ""
            for cand in (os.path.dirname(exe), os.path.join(os.path.dirname(exe), "_internal"),
                         getattr(sys, "_MEIPASS", None)):
                if cand and cand not in sys.path:
                    try:
                        sys.path.insert(0, cand)
                    except Exception:
                        pass
            if install():
                _log("gif fix installed")
                return
        except Exception as e:
            last = e
            if not told:
                told = True
                _log("not ready yet: %r" % (e,))
        time.sleep(0.5)
    _log("gif fix FAILED after retries: %r" % (last,))
    _error_log("install failed after retries: %r\n" % (last,))


threading.Thread(target=_worker, daemon=True).start()
