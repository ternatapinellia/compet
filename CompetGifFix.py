# CompetGifFix.py
# ---------------------------------------------------------------------------
# Runtime animated-image (GIF / WebP) support for the Compet desktop pet.
#
# CompetGifFix.dll reads this file and executes it inside a running Compet.exe.
# It patches ui.pet_widget.PetWidget so that a skin whose image is a ".gif" or
# ".webp" animation is played frame by frame.
#
# Safety:
#   * Skins made of ordinary still images (png / jpg / ...) are left completely
#     untouched: every patched method delegates to the original implementation
#     unless the pet actually loaded an animation.
#   * Nothing on disk is modified.  Restarting Compet reverts everything.
# ---------------------------------------------------------------------------

import os
import time

_FRAME_INTERVAL_MS = 33          # ~30 fps repaint cadence
_ANIM_EXTS = (".gif", ".webp")

QMovie = None


def _is_anim(path):
    try:
        return str(path).lower().endswith(_ANIM_EXTS)
    except Exception:
        return False


def _make_movie(path, size=None):
    """Return a running QMovie, or None when *path* is not a real animation."""
    from PyQt6.QtGui import QMovie as _Movie, QImageReader
    from PyQt6.QtCore import QSize

    try:
        if not (os.path.exists(path) and _is_anim(path)):
            return None
    except Exception:
        return None

    try:
        reader = QImageReader(path)
        if not reader.supportsAnimation() or reader.imageCount() <= 1:
            return None
    except Exception:
        pass

    try:
        mv = _Movie(path)
        mv.setCacheMode(_Movie.CacheMode.CacheAll)
        if size is not None and size[0] > 0 and size[1] > 0:
            mv.setScaledSize(QSize(int(size[0]), int(size[1])))
        mv.jumpToFrame(0)
        if not mv.isValid():
            return None
        return mv
    except Exception:
        return None


def _frame_size(mv):
    pm = mv.currentPixmap()
    if pm is None or pm.isNull():
        return (0, 0)
    return (pm.width(), pm.height())


def install():
    """Patch PetWidget in place.  Safe to call more than once."""
    global QMovie

    import ui.pet_widget as pw
    from PyQt6.QtGui import QPainter, QMovie as _Movie
    from PyQt6.QtCore import QTimer
    QMovie = _Movie

    PetWidget = pw.PetWidget
    if getattr(PetWidget, "_compet_anim_patched", False):
        return True

    orig_load = PetWidget.load_resources
    orig_bounce = PetWidget.trigger_bounce
    orig_reset = PetWidget.reset_to_idle
    orig_size = PetWidget.update_widget_size
    orig_paint = PetWidget.paintEvent

    # ---- internal helpers -------------------------------------------------

    def _anim_on(self):
        return getattr(self, "_anim_enabled", False)

    def _activate(self):
        cur = getattr(self, "_current_anim", None)
        cache = getattr(self, "_movie_cache", None)
        if cache:
            for mv in set(cache.values()):
                if mv is None:
                    continue
                try:
                    if mv is cur:
                        if mv.state() == QMovie.MovieState.NotRunning:
                            mv.start()
                    elif mv.state() != QMovie.MovieState.NotRunning:
                        mv.stop()
                except Exception:
                    pass
        ticker = getattr(self, "_anim_ticker", None)
        if ticker is not None:
            try:
                if cur is not None:
                    ticker.start(_FRAME_INTERVAL_MS)
                else:
                    ticker.stop()
            except Exception:
                pass

    def _set_current(self, key):
        self.current_pixmap = self.cached_pixmaps.get(key, self.current_pixmap)
        self._current_anim = self.animations.get(key)
        _activate(self)

    def _set_tap(self, idx):
        try:
            pm = self.tap_pixmaps[idx]
        except Exception:
            pm = None
        if pm is not None:
            self.current_pixmap = pm
        self._current_anim = self.animations.get("tap%d" % idx)
        _activate(self)

    # ---- patched methods --------------------------------------------------

    def load_resources(self):
        orig_load(self)
        self._anim_enabled = False
        self._current_anim = None
        self._idle_movie = None
        self.animations = {}
        self._movie_cache = {}
        try:
            skin = self.instance_data.get("skin", "default")
            try:
                conf = pw.config_mgr.get_skin_config(skin)
            except Exception:
                conf = {}
            s_dir = os.path.join(pw.SKINS_DIR, skin)

            def movie(path, size=None):
                key = (os.path.normcase(path), size)
                if key not in self._movie_cache:
                    self._movie_cache[key] = _make_movie(path, size)
                return self._movie_cache[key]

            idle_movie = movie(os.path.join(s_dir, conf.get("idle_image", "idle.png")))
            if idle_movie is None:
                return  # still image skin -> keep 100% original behaviour

            iw, ih = _frame_size(idle_movie)
            first = idle_movie.currentPixmap()
            if first is not None and not first.isNull():
                self.idle_pixmap = first
            ref = (iw, ih) if iw and ih else None

            for k, v in list(self.key_mappings.items()):
                m = movie(os.path.join(s_dir, v), ref)
                if m is None:
                    continue
                key = str(k).strip()
                pm = m.currentPixmap()
                self.animations[key] = m
                self.animations[key.lower()] = m
                if pm is not None and not pm.isNull():
                    self.cached_pixmaps[key] = pm
                    self.cached_pixmaps[key.lower()] = pm

            for idx, name in enumerate(conf.get("tap_images", ["tap_left.png", "tap_right.png"])):
                m = movie(os.path.join(s_dir, name), ref)
                if m is not None:
                    self.animations["tap%d" % idx] = m

            if getattr(self, "_anim_ticker", None) is None:
                t = QTimer(self)
                t.setSingleShot(False)
                t.timeout.connect(lambda: self.update())
                self._anim_ticker = t

            self._idle_movie = idle_movie
            self._current_anim = idle_movie
            self.current_pixmap = self.idle_pixmap
            self._anim_enabled = True
            _activate(self)
            self.update_widget_size()
            self.update()
        except Exception:
            self._anim_enabled = False

    def trigger_bounce(self, key_payload):
        if not _anim_on(self):
            return orig_bounce(self, key_payload)

        now = time.time()
        self.hit_times.append(now)
        apm = 0
        if len(self.hit_times) > 1:
            dt = now - self.hit_times[0]
            if dt > 0:
                apm = len(self.hit_times) / dt * 60

        candidates = [c.strip() for c in key_payload.split("|") if c.strip()]
        matched = None
        for cand in candidates:
            if cand in self.cached_pixmaps and not self.cached_pixmaps[cand].isNull():
                matched = cand
                break
            lower = cand.lower()
            if lower in self.cached_pixmaps and not self.cached_pixmaps[lower].isNull():
                matched = lower
                break

        if matched is not None:
            _set_current(self, matched)
        elif any(c.startswith("mouse_") for c in candidates) and "mouse_click" in self.cached_pixmaps:
            _set_current(self, "mouse_click")
        elif self.tap_pixmaps:
            _set_tap(self, self.tap_index)
            self.tap_index = (self.tap_index + 1) % len(self.tap_pixmaps)

        extra_squash = min(apm / 600.0, 1.0) * 0.08
        actual_depth = min(self.squash_depth + extra_squash, 0.75)
        self.scale_y = max(0.2, 1.0 - actual_depth)
        self.scale_x = 1.0 + actual_depth * 0.5

        self.reset_timer.start(240 if matched is not None else 160)
        self.anim_timer.start(16)
        self.update()

    def reset_to_idle(self):
        if not _anim_on(self):
            return orig_reset(self)
        self._current_anim = getattr(self, "_idle_movie", None)
        self.current_pixmap = self.idle_pixmap
        _activate(self)
        self.update()

    def update_widget_size(self):
        if not _anim_on(self):
            return orig_size(self)
        anim = getattr(self, "_idle_movie", None)
        pm = anim.currentPixmap() if anim is not None else self.idle_pixmap
        if pm is None or pm.isNull():
            return
        self.resize(max(40, int(pm.width() * self.display_scale)),
                    max(40, int(pm.height() * self.display_scale)))

    def paintEvent(self, event):
        if not _anim_on(self):
            return orig_paint(self, event)
        anim = getattr(self, "_current_anim", None)
        pm = anim.currentPixmap() if anim is not None else self.current_pixmap
        if pm is None or pm.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(self.display_scale * self.scale_x,
                      self.display_scale * self.scale_y)
        painter.translate(-pm.width() / 2, -pm.height() / 2)
        painter.drawPixmap(0, 0, pm)

    PetWidget.load_resources = load_resources
    PetWidget.trigger_bounce = trigger_bounce
    PetWidget.reset_to_idle = reset_to_idle
    PetWidget.update_widget_size = update_widget_size
    PetWidget.paintEvent = paintEvent
    PetWidget._compet_anim_patched = True

    # Refresh pets that are already on screen.
    try:
        from PyQt6.QtWidgets import QApplication
        for w in QApplication.topLevelWidgets():
            if isinstance(w, PetWidget):
                w.load_resources()
    except Exception:
        pass
    return True


try:
    install()
except Exception:
    import traceback
    try:
        with open(os.path.join(os.path.expanduser("~"), "_compet_gif_fix_error.log"),
                  "a", encoding="utf-8") as fh:
            fh.write(traceback.format_exc())
    except Exception:
        pass