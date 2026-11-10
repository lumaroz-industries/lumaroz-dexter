"""
Lumaroz live wallpaper — 夜の牙 (Yoru no Kiba, "Night Fang").

The animated scene behind Dexter's face. Two modes:

  SCENE   A Japanese night painted entirely in code: a blood moon that breathes,
          cloud wisps sliding across it, three ranges of mountains, a pagoda
          with flickering lanterns, a torii on the far shore, overhanging momiji
          branches that sway, a lake that mirrors all of it with a rippling moon
          path, drifting mist, falling maple leaves and rising embers.

  IMAGE   Any still picture turned into a live wallpaper: a slow looping camera
          drift, a breathing light, mist along the bottom, falling leaves and
          embers in front. Point it at your own art, or ask Dexter to generate
          one ("Dexter, make me a wallpaper of a Kyoto street in the rain").

PERFORMANCE
    Everything that does not move is rendered ONCE per window size into a
    pixmap: sky, moon body, mountains, buildings, vignette. A frame is then a
    handful of blits plus ~60 small particles and ~100 thin reflection strips,
    which costs about what the avatar mesh in front of it does.

Qt-thread only. No network, no files beyond the optional wallpaper image.
"""
from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPainterPath,
                         QPen, QPixmap, QRadialGradient, QTransform)

# ── palette (independent of the UI accent so the scene keeps its mood) ──────
SKY_TOP    = QColor("#040106")
SKY_MID    = QColor("#14040a")
SKY_LOW    = QColor("#3b0a10")
HAZE       = QColor("#6e1218")
MOON_CORE  = QColor("#ff6b55")
MOON_MID   = QColor("#d0222c")
MOON_EDGE  = QColor("#6a0910")
RIDGE_FAR  = QColor("#4a121b")
RIDGE_MID  = QColor("#290a10")
RIDGE_NEAR = QColor("#110407")
INK        = QColor("#050102")
LANTERN    = QColor("#ff7a3a")
LEAF_COLS  = (QColor("#e0182c"), QColor("#b80f22"), QColor("#ff3b2f"),
              QColor("#8f0c1a"), QColor("#ff5a36"))
EMBER      = QColor("#ff9a5a")
GOLD       = QColor("#e8b866")

MOTION_LEVELS = ("full", "calm", "off")


def _alpha(c: QColor, a: float) -> QColor:
    q = QColor(c)
    q.setAlphaF(max(0.0, min(1.0, a)))
    return q


def _maple_path() -> QPainterPath:
    """A five-lobed momiji leaf, unit size, pointing up, with a short stem."""
    path = QPainterPath()
    n = 90
    for i in range(n + 1):
        th = (i / n) * math.tau
        lobes = abs(math.cos(2.5 * (th - math.pi / 2))) ** 0.55
        teeth = 0.06 * math.sin(th * 25)
        r = 0.42 + 0.58 * lobes + teeth * lobes
        if math.sin(th) > 0.55:          # flatten the bottom where the stem is
            r *= 0.62
        x, y = r * math.cos(th - math.pi / 2), r * math.sin(th - math.pi / 2)
        y = -y
        (path.moveTo if i == 0 else path.lineTo)(x, y)
    path.closeSubpath()
    path.moveTo(0, 0.25)
    path.lineTo(0.04, 0.95)
    path.lineTo(-0.02, 0.95)
    path.closeSubpath()
    return path


_LEAF = _maple_path()


class _Leaf:
    __slots__ = ("x", "y", "vx", "vy", "rot", "vrot", "size", "phase", "col", "flip")

    def __init__(self, W: float, H: float, rng: random.Random, anywhere: bool):
        self.reset(W, H, rng, anywhere)

    def reset(self, W, H, rng, anywhere=False):
        self.x = rng.uniform(-0.1, 1.05) * W
        self.y = rng.uniform(-0.1, 1.0) * H if anywhere else rng.uniform(-0.25, -0.03) * H
        self.vx = rng.uniform(8, 26)
        self.vy = rng.uniform(22, 48)
        self.rot = rng.uniform(0, 360)
        self.vrot = rng.uniform(-70, 70)
        self.size = rng.uniform(5.5, 13.0) * max(0.7, min(1.6, H / 800))
        self.phase = rng.uniform(0, math.tau)
        self.col = rng.choice(LEAF_COLS)
        self.flip = rng.uniform(0.6, 1.4)


class _Ember:
    __slots__ = ("x", "y", "vy", "r", "phase", "drift")

    def __init__(self, W, H, rng, anywhere=True):
        self.reset(W, H, rng, anywhere)

    def reset(self, W, H, rng, anywhere=False):
        self.x = rng.uniform(0, W)
        self.y = rng.uniform(0.35, 1.0) * H if anywhere else H + rng.uniform(0, 40)
        self.vy = rng.uniform(6, 20)
        self.r = rng.uniform(0.8, 2.2)
        self.phase = rng.uniform(0, math.tau)
        self.drift = rng.uniform(-6, 6)


class LiveWallpaper:
    """Call paint(p, W, H, t, amp) from a paintEvent. `t` is seconds (monotonic),
    `amp` the 0–1 voice level, which makes the moon and mist answer the voice."""

    def __init__(self, image: str = "", motion: str = "full", seed: int = 1987):
        self._seed = seed
        self._rng = random.Random(seed)
        self.motion = motion if motion in MOTION_LEVELS else "full"
        self._size = (0, 0)
        self._static: Optional[QPixmap] = None      # sky..buildings (above water)
        self._mirror: Optional[QPixmap] = None      # flipped + darkened, for the lake
        self._branches: list[tuple[QPixmap, QPointF, QPointF, float]] = []
        self._vignette: Optional[QPixmap] = None
        self._mist: list[QPixmap] = []
        self._leaves: list[_Leaf] = []
        self._embers: list[_Ember] = []
        self._last_t: Optional[float] = None
        self._image_path = ""
        self._image_src: Optional[QPixmap] = None
        self._image_fit: Optional[QPixmap] = None
        self._lanterns: list[QPointF] = []
        self.set_image(image)

    # ── configuration ────────────────────────────────────────────────────
    @property
    def image_path(self) -> str:
        return self._image_path

    def set_image(self, path: str) -> bool:
        """Use a still picture as the wallpaper ("" returns to the scene)."""
        path = str(path or "").strip()
        if path:
            px = QPixmap(path)
            if px.isNull():
                return False
            self._image_src = px
        else:
            self._image_src = None
        self._image_path = path
        self._image_fit = None
        self._size = (0, 0)          # force a rebuild at the next paint
        return True

    def set_motion(self, motion: str) -> None:
        if motion in MOTION_LEVELS:
            self.motion = motion
            self._size = (0, 0)

    # ── static layers ────────────────────────────────────────────────────
    def _horizon(self, H: float) -> float:
        return H * 0.64

    def _ridge(self, W, H, base, amp, freq, seed) -> QPainterPath:
        r = random.Random(seed)
        waves = [(r.uniform(0.6, 1.0) / (k + 1), freq * (k + 1) * r.uniform(0.8, 1.25),
                  r.uniform(0, math.tau)) for k in range(5)]
        peaks = [(r.uniform(0.05, 0.95) * W, r.uniform(0.4, 1.0)) for _ in range(3)]
        path = QPainterPath()
        path.moveTo(0, H)
        steps = max(60, int(W / 6))
        for i in range(steps + 1):
            x = W * i / steps
            y = sum(a * math.sin(x / W * f * math.tau + ph) for a, f, ph in waves)
            for px, ph in peaks:                         # a few proud summits
                d = (x - px) / (W * 0.09)
                y += ph * 1.6 * math.exp(-d * d)
            path.lineTo(x, base - amp * (0.5 + 0.35 * y))
        path.lineTo(W, H)
        path.closeSubpath()
        return path

    def _pagoda(self, p: QPainter, x: float, base: float, s: float) -> None:
        """A five-storey pagoda, `s` tall, with sweeping upturned eaves."""
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(INK)
        self._lanterns.clear()
        y = base
        p.drawRect(QRectF(x - s * 0.30, y - s * 0.035, s * 0.60, s * 0.035))   # stone plinth
        y -= s * 0.035
        for tier in range(5):
            k = 1.0 - tier * 0.11
            bw, bh = s * 0.26 * k, s * 0.085 * (1.0 - tier * 0.05)
            p.drawRect(QRectF(x - bw / 2, y - bh, bw, bh))
            self._lanterns.append(QPointF(x, y - bh * 0.45))
            y -= bh
            rw, rt = s * 0.56 * k, s * 0.05 * k                 # roof span, thickness
            roof = QPainterPath()
            roof.moveTo(x - rw / 2, y - rt * 1.25)                # upturned left tip
            roof.quadTo(x - rw * 0.34, y + rt * 0.15, x - bw * 0.30, y - rt * 0.55)
            roof.quadTo(x, y - rt * 1.6, x + bw * 0.30, y - rt * 0.55)
            roof.quadTo(x + rw * 0.34, y + rt * 0.15, x + rw / 2, y - rt * 1.25)
            roof.quadTo(x + rw * 0.30, y - rt * 0.9, x + bw * 0.18, y - rt * 2.0)
            roof.lineTo(x - bw * 0.18, y - rt * 2.0)
            roof.quadTo(x - rw * 0.30, y - rt * 0.9, x - rw / 2, y - rt * 1.25)
            roof.closeSubpath()
            p.drawPath(roof)
            y -= rt * 1.9
        p.drawRect(QRectF(x - s * 0.007, y - s * 0.19, s * 0.014, s * 0.19))  # sorin spire
        for k in range(7):
            p.drawEllipse(QPointF(x, y - s * (0.03 + k * 0.022)), s * 0.022, s * 0.006)
        p.drawEllipse(QPointF(x, y - s * 0.2), s * 0.012, s * 0.012)

    def _torii(self, p: QPainter, x: float, base: float, s: float) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(INK)
        h = s * 1.0
        for dx in (-0.36, 0.36):
            col = QPainterPath()
            px = x + dx * s
            col.moveTo(px - s * 0.035, base)
            col.lineTo(px - s * 0.028, base - h)
            col.lineTo(px + s * 0.028, base - h)
            col.lineTo(px + s * 0.035, base)
            col.closeSubpath()
            p.drawPath(col)
        p.drawRect(QRectF(x - s * 0.47, base - h * 0.74, s * 0.94, s * 0.045))  # nuki
        p.drawRect(QRectF(x - s * 0.02, base - h * 0.94, s * 0.04, h * 0.2))    # gakuzuka
        kasagi = QPainterPath()
        kasagi.moveTo(x - s * 0.62, base - h * 1.04)
        kasagi.quadTo(x, base - h * 0.93, x + s * 0.62, base - h * 1.04)
        kasagi.lineTo(x + s * 0.58, base - h * 0.97)
        kasagi.quadTo(x, base - h * 0.88, x - s * 0.58, base - h * 0.97)
        kasagi.closeSubpath()
        p.drawPath(kasagi)
        p.drawRect(QRectF(x - s * 0.5, base - h * 0.93, s * 1.0, s * 0.04))     # shimaki

    def _branch(self, W, H, left: bool, seed: int) -> tuple[QPixmap, QPointF, QPointF]:
        """An overhanging momiji branch, drawn into its own pixmap so it can sway."""
        bw, bh = int(W * 0.50), int(H * 0.60)
        reach = W * 0.34              # how far the limbs extend; the rest is margin
        pm = QPixmap(max(1, bw), max(1, bh))
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = random.Random(seed)
        ox = 0 if left else bw
        sign = 1 if left else -1
        tips = []

        def limb(x0, y0, ang, length, width, depth):
            x1 = x0 + math.cos(ang) * length * sign
            y1 = y0 + math.sin(ang) * length
            pen = QPen(INK, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            q.setPen(pen)
            cx = (x0 + x1) / 2 + r.uniform(-12, 12)
            cy = (y0 + y1) / 2 + r.uniform(-14, 6)
            path = QPainterPath(QPointF(x0, y0))
            path.quadTo(cx, cy, x1, y1)
            q.drawPath(path)
            if depth > 0:
                for _ in range(2 if depth > 1 else 3):
                    limb(x1, y1, ang + r.uniform(-0.6, 0.7), length * r.uniform(0.55, 0.75),
                         max(1.0, width * 0.62), depth - 1)
            else:
                tips.append((x1, y1))

        limb(ox, H * 0.03, 0.22, reach * 0.46, max(5.0, W / 170), 3)
        limb(ox, 0.0, 0.62, reach * 0.30, max(4.0, W / 220), 2)
        q.setPen(Qt.PenStyle.NoPen)
        for tx, ty in tips:                                   # foliage clusters
            for _ in range(r.randint(9, 15)):
                lx = tx + r.gauss(0, reach * 0.06)
                ly = ty + r.gauss(0, H * 0.023)
                sz = r.uniform(4, 9) * max(0.8, H / 800)
                c = QColor(r.choice(LEAF_COLS))
                c.setAlphaF(r.uniform(0.75, 1.0))
                q.save()
                q.translate(lx, ly)
                q.rotate(r.uniform(-60, 60))
                q.scale(sz, sz)
                q.setBrush(c)
                q.drawPath(_LEAF)
                q.restore()
        q.end()
        anchor = QPointF(0 if left else W - bw, 0)
        pivot = QPointF(ox, 0)
        return pm, anchor, pivot

    def _build(self, W: int, H: int) -> None:
        self._size = (W, H)
        self._rng = random.Random(self._seed)
        hz = self._horizon(H)

        # vignette (both modes)
        vg = QPixmap(W, H)
        vg.fill(Qt.GlobalColor.transparent)
        q = QPainter(vg)
        rg = QRadialGradient(QPointF(W / 2, H * 0.45), max(W, H) * 0.75)
        rg.setColorAt(0.0, QColor(0, 0, 0, 0))
        rg.setColorAt(0.6, QColor(0, 0, 0, 40))
        rg.setColorAt(1.0, QColor(0, 0, 0, 205))
        q.fillRect(0, 0, W, H, QBrush(rg))
        q.end()
        self._vignette = vg

        # one soft ember sprite, reused for every ember
        spr = QPixmap(32, 32)
        spr.fill(Qt.GlobalColor.transparent)
        q = QPainter(spr)
        g = QRadialGradient(QPointF(16, 16), 16)
        g.setColorAt(0.0, _alpha(EMBER, 1.0))
        g.setColorAt(0.25, _alpha(EMBER, 0.55))
        g.setColorAt(1.0, _alpha(EMBER, 0.0))
        q.fillRect(spr.rect(), QBrush(g))
        q.end()
        self._ember_sprite = spr

        _, _, mr = self.moon_geom(W, H)
        hr = mr * 2.6
        halo = QPixmap(int(hr * 2), int(hr * 2))
        halo.fill(Qt.GlobalColor.transparent)
        q = QPainter(halo)
        hg = QRadialGradient(QPointF(hr, hr), hr)
        red = QColor("#ff3a3a")
        hg.setColorAt(0.0, _alpha(red, 0.0))
        hg.setColorAt(mr / hr * 0.98, _alpha(red, 0.5))
        hg.setColorAt(mr / hr * 1.6, _alpha(red, 0.14))
        hg.setColorAt(1.0, _alpha(red, 0.0))
        q.fillRect(halo.rect(), QBrush(hg))
        q.end()
        self._halo_sprite = halo
        cw, ch = int(mr * 3.6), max(4, int(mr * 0.22))
        cloud = QPixmap(cw, ch)
        cloud.fill(Qt.GlobalColor.transparent)
        q = QPainter(cloud)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        cg = QRadialGradient(QPointF(cw / 2, ch / 2), cw / 2)
        cg.setColorAt(0.0, QColor(30, 4, 8, 100))
        cg.setColorAt(1.0, QColor(30, 4, 8, 0))
        q.setBrush(QBrush(cg)); q.setPen(Qt.PenStyle.NoPen)
        q.drawEllipse(QRectF(0, 0, cw, ch))
        q.end()
        self._cloud_sprite = cloud

        # mist banks
        self._mist = []
        for k in range(3):
            mw, mh = int(W * 0.9), int(H * (0.16 + 0.05 * k))
            m = QPixmap(max(1, mw), max(1, mh))
            m.fill(Qt.GlobalColor.transparent)
            q = QPainter(m)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            for j in range(7):
                cx = mw * (0.1 + 0.8 * j / 6) + self._rng.uniform(-40, 40)
                g = QRadialGradient(QPointF(cx, mh / 2), mw * 0.18)
                tint = QColor(150, 40, 48) if k else QColor(190, 70, 70)
                g.setColorAt(0.0, _alpha(tint, 0.10 if k else 0.13))
                g.setColorAt(1.0, _alpha(tint, 0.0))
                q.setBrush(QBrush(g))
                q.setPen(Qt.PenStyle.NoPen)
                q.drawEllipse(QPointF(cx, mh / 2), mw * 0.2, mh * 0.5)
            q.end()
            self._mist.append(m)

        # particles
        n_leaf = {"full": 34, "calm": 14, "off": 0}[self.motion]
        n_emb = {"full": 30, "calm": 12, "off": 0}[self.motion]
        self._leaves = [_Leaf(W, H, self._rng, True) for _ in range(n_leaf)]
        self._embers = [_Ember(W, H, self._rng, True) for _ in range(n_emb)]

        if self._image_src is not None:
            # cover-fit, with 10% headroom for the camera drift
            sw, sh = self._image_src.width(), self._image_src.height()
            k = max(W / sw, H / sh) * 1.10
            self._image_fit = self._image_src.scaled(
                int(sw * k) + 2, int(sh * k) + 2,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._static = self._mirror = None
            self._branches = []
            return

        # ── the painted scene ────────────────────────────────────────────
        st = QPixmap(W, int(hz) + 1)
        st.fill(SKY_TOP)
        q = QPainter(st)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        sky = QLinearGradient(0, 0, 0, hz)
        sky.setColorAt(0.0, SKY_TOP)
        sky.setColorAt(0.45, SKY_MID)
        sky.setColorAt(0.85, SKY_LOW)
        sky.setColorAt(1.0, HAZE)
        q.fillRect(QRectF(0, 0, W, hz + 1), QBrush(sky))
        q.setPen(Qt.PenStyle.NoPen)
        for _ in range(int(W * H / 9000)):                       # faint stars
            sx, sy = self._rng.uniform(0, W), self._rng.uniform(0, hz * 0.55)
            q.setBrush(_alpha(QColor("#ffd9d0"), self._rng.uniform(0.15, 0.6)))
            q.drawEllipse(QPointF(sx, sy), 0.7, 0.7)

        # moon body
        mx, my, mr = self.moon_geom(W, H)
        mg = QRadialGradient(QPointF(mx - mr * 0.25, my - mr * 0.25), mr * 1.25)
        mg.setColorAt(0.0, MOON_CORE)
        mg.setColorAt(0.55, MOON_MID)
        mg.setColorAt(1.0, MOON_EDGE)
        q.setBrush(QBrush(mg))
        q.drawEllipse(QPointF(mx, my), mr, mr)
        q.save()
        clip = QPainterPath()
        clip.addEllipse(QPointF(mx, my), mr, mr)
        q.setClipPath(clip)
        for _ in range(26):                                      # maria and craters
            a = self._rng.uniform(0, math.tau)
            d = self._rng.uniform(0, mr * 0.9)
            cr = self._rng.uniform(mr * 0.04, mr * 0.28)
            cg = QRadialGradient(QPointF(mx + math.cos(a) * d, my + math.sin(a) * d), cr)
            cg.setColorAt(0.0, QColor(70, 0, 8, self._rng.randint(40, 110)))
            cg.setColorAt(1.0, QColor(70, 0, 8, 0))
            q.setBrush(QBrush(cg))
            q.drawEllipse(QPointF(mx + math.cos(a) * d, my + math.sin(a) * d), cr, cr)
        q.restore()

        # mountains
        q.setBrush(RIDGE_FAR)
        q.drawPath(self._ridge(W, hz, hz * 0.94, hz * 0.42, 2.2, self._seed + 1))
        hg = QLinearGradient(0, hz * 0.55, 0, hz)               # haze between ranges
        hg.setColorAt(0.0, _alpha(HAZE, 0.0))
        hg.setColorAt(1.0, _alpha(HAZE, 0.35))
        q.fillRect(QRectF(0, hz * 0.55, W, hz * 0.45), QBrush(hg))
        q.setBrush(RIDGE_MID)
        q.drawPath(self._ridge(W, hz, hz * 0.99, hz * 0.26, 3.1, self._seed + 2))
        q.setBrush(RIDGE_NEAR)
        q.drawPath(self._ridge(W, hz, hz * 1.02, hz * 0.12, 4.6, self._seed + 3))

        # shores, pagoda, torii
        s = min(W, H)
        shore_l = QPainterPath()
        shore_l.moveTo(0, hz - s * 0.05)
        shore_l.quadTo(W * 0.16, hz - s * 0.065, W * 0.27, hz)
        shore_l.lineTo(0, hz)
        shore_l.closeSubpath()
        q.setBrush(INK)
        q.drawPath(shore_l)
        self._pagoda(q, W * 0.13, hz - s * 0.05, s * 0.36)
        shore_r = QPainterPath()
        shore_r.moveTo(W, hz - s * 0.03)
        shore_r.quadTo(W * 0.88, hz - s * 0.035, W * 0.80, hz)
        shore_r.lineTo(W, hz)
        shore_r.closeSubpath()
        q.drawPath(shore_r)
        self._torii(q, W * 0.905, hz - s * 0.03, s * 0.16)
        for _ in range(14):                                       # pines on the shores
            tx = self._rng.choice((self._rng.uniform(0.0, 0.25), self._rng.uniform(0.82, 1.0))) * W
            th = self._rng.uniform(0.05, 0.11) * s
            pine = QPainterPath()
            pine.moveTo(tx, hz - th - s * 0.03)
            pine.lineTo(tx + th * 0.28, hz - s * 0.02)
            pine.lineTo(tx - th * 0.28, hz - s * 0.02)
            pine.closeSubpath()
            q.drawPath(pine)
        q.end()
        self._static = st

        # the lake's mirror image: flipped, darker, a little red
        mir = st.transformed(QTransform().scale(1, -1))
        q = QPainter(mir)
        q.fillRect(mir.rect(), QColor(8, 0, 3, 70))
        q.end()
        # Pre-scale the part of the mirror the lake shows to exactly the lake's
        # height, so every ripple strip per frame is a 1:1 copy, not a rescale.
        depth = max(1, int(H - hz) + 1)
        self._mirror = mir.copy(0, 0, mir.width(), min(mir.height(), depth)).scaled(
            W, depth, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation)

        self._branches = []
        if self.motion != "off" or True:
            for left, seed in ((True, self._seed + 10), (False, self._seed + 11)):
                pm, anchor, pivot = self._branch(W, H, left, seed)
                self._branches.append((pm, anchor, pivot, 1.0 if left else -1.0))

    def moon_geom(self, W: float, H: float) -> tuple[float, float, float]:
        r = min(W, H) * 0.115
        return W * 0.80, H * 0.22, r

    # ── per-frame ────────────────────────────────────────────────────────
    def _advance(self, W, H, t: float) -> float:
        dt = 0.0 if self._last_t is None else max(0.0, min(0.1, t - self._last_t))
        self._last_t = t
        if self.motion == "off":
            return dt
        gust = 1.0 + 0.8 * max(0.0, math.sin(t * 0.21)) ** 3
        for lf in self._leaves:
            lf.x += (lf.vx * gust + 26 * math.sin(t * 0.9 + lf.phase)) * dt
            lf.y += lf.vy * dt
            lf.rot += lf.vrot * dt
            if lf.y > H + 20 or lf.x > W + 40:
                lf.reset(W, H, self._rng)
        for e in self._embers:
            e.y -= e.vy * dt
            e.x += (e.drift + 5 * math.sin(t * 0.7 + e.phase)) * dt
            if e.y < H * 0.25:
                e.reset(W, H, self._rng)
        return dt

    def paint(self, p: QPainter, W: int, H: int, t: float, amp: float = 0.0) -> None:
        if W < 4 or H < 4:
            return
        if (W, H) != self._size:
            self._build(W, H)
        self._advance(W, H, t)
        calm = self.motion == "off"
        tt = 0.0 if calm else t

        if self._image_fit is not None:
            self._paint_image(p, W, H, tt)
        else:
            self._paint_scene(p, W, H, tt, amp)

        # mist (both modes)
        for k, m in enumerate(self._mist):
            speed = (7, 4, 10)[k]
            y = (self._horizon(H) - m.height() * 0.55 if self._image_fit is None
                 else H * (0.70 + 0.08 * k) - m.height() / 2) + k * H * 0.05
            off = (tt * speed + k * W * 0.33) % (m.width())
            p.setOpacity(0.85 + 0.15 * amp)
            for x in (-off, -off + m.width(), -off + 2 * m.width()):
                if x < W:
                    p.drawPixmap(QPointF(x, y), m)
            p.setOpacity(1.0)

        p.setPen(Qt.PenStyle.NoPen)
        spr = self._ember_sprite
        for e in self._embers:                                 # rising embers
            p.setOpacity(0.35 + 0.45 * (0.5 + 0.5 * math.sin(tt * 3.1 + e.phase)))
            d = e.r * 8
            p.drawPixmap(QRectF(e.x - d / 2, e.y - d / 2, d, d), spr, QRectF(spr.rect()))
        p.setOpacity(1.0)

        for lf in self._leaves:                                # falling momiji
            p.save()
            p.translate(lf.x, lf.y)
            p.rotate(lf.rot)
            p.scale(lf.size * abs(math.sin(tt * lf.flip + lf.phase)) * 0.75 + lf.size * 0.25,
                    lf.size)
            p.setBrush(lf.col)
            p.drawPath(_LEAF)
            p.restore()

        if self._vignette is not None:
            p.drawPixmap(0, 0, self._vignette)

    def _paint_image(self, p: QPainter, W, H, t):
        img = self._image_fit
        ex, ey = img.width() - W, img.height() - H
        # a slow looping figure-of-eight drift, 90 s per loop
        fx = 0.5 + 0.5 * math.sin(t * math.tau / 90)
        fy = 0.5 + 0.5 * math.sin(t * math.tau / 45 + 1.2)
        p.drawPixmap(QPointF(-ex * fx, -ey * fy), img)
        breathe = 0.5 + 0.5 * math.sin(t * 0.35)
        p.fillRect(QRectF(0, 0, W, H), QColor(10, 0, 4, int(40 + 35 * breathe)))
        glow = QLinearGradient(0, H * 0.55, 0, H)
        glow.setColorAt(0.0, QColor(120, 10, 20, 0))
        glow.setColorAt(1.0, QColor(120, 10, 20, int(40 + 30 * breathe)))
        p.fillRect(QRectF(0, H * 0.55, W, H * 0.45), QBrush(glow))

    def _paint_scene(self, p: QPainter, W, H, t, amp):
        hz = self._horizon(H)
        p.drawPixmap(0, 0, self._static)
        mx, my, mr = self.moon_geom(W, H)

        # breathing moon halo, brightening with the voice
        pulse = 0.5 + 0.5 * math.sin(t * 0.5)
        halo = self._halo_sprite
        p.setOpacity(min(1.0, 0.70 + 0.22 * pulse + 0.3 * amp))
        p.drawPixmap(int(mx - halo.width() / 2), int(my - halo.height() / 2), halo)

        # cloud wisps drifting across the moon
        cloud = self._cloud_sprite
        p.setOpacity(1.0)
        for k in range(3):
            cw = cloud.width()
            cx = ((t * (6 + 3 * k) + k * 400) % (W + cw * 2)) - cw * 1.5
            cy = my + mr * (-0.45 + 0.5 * k) - cloud.height() / 2
            p.drawPixmap(int(cx), int(cy), cloud)
        p.setPen(Qt.PenStyle.NoPen)

        # lantern flicker on the pagoda
        for i, pt in enumerate(self._lanterns):
            f = 0.55 + 0.45 * math.sin(t * (5.0 + i) + i * 1.7) * math.sin(t * 2.3 + i)
            lr = H * 0.009
            lg = QRadialGradient(pt, lr)
            lg.setColorAt(0.0, _alpha(LANTERN, 0.6 + 0.4 * f))
            lg.setColorAt(1.0, _alpha(LANTERN, 0.0))
            p.setBrush(QBrush(lg))
            p.drawEllipse(pt, lr, lr)

        # ── the lake ────────────────────────────────────────────────────
        water = QLinearGradient(0, hz, 0, H)
        water.setColorAt(0.0, QColor("#1a0408"))
        water.setColorAt(1.0, QColor("#040103"))
        p.fillRect(QRectF(0, hz, W, H - hz), QBrush(water))
        mir = self._mirror
        depth = mir.height()
        y = 0
        top = int(hz)
        while y < depth:
            k = y / depth
            strip = 3 if k < 0.3 else 5           # finer ripples near the shore
            dx = math.sin(t * 1.3 + y * 0.09) * (1.5 + 9 * k) + math.sin(t * 0.7 + y * 0.031) * 3 * k
            p.setOpacity(0.72 * (1.0 - 0.45 * k))
            p.drawPixmap(int(dx), top + y, mir, 0, y, W, strip)
            y += strip
        p.setOpacity(1.0)

        # the moon's path on the water: glittering dashes
        rng = random.Random(int(t * 4))
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(46):
            yy = hz + 4 + (i / 46) ** 1.3 * depth * 0.95
            spread = mr * (0.35 + 1.6 * (yy - hz) / depth)
            xx = mx + rng.uniform(-spread, spread) + math.sin(t * 1.5 + i) * 4
            ln = rng.uniform(6, 26) * (0.6 + (yy - hz) / depth)
            a = 0.25 + 0.5 * rng.random()
            p.setBrush(_alpha(QColor("#ff5e4e"), a * (1 - (yy - hz) / depth * 0.6)))
            p.drawRoundedRect(QRectF(xx - ln / 2, yy, ln, 1.6), 0.8, 0.8)
        hl = QLinearGradient(0, hz - 2, 0, hz + 6)                    # shoreline glint
        hl.setColorAt(0.0, QColor(255, 80, 70, 0))
        hl.setColorAt(0.5, QColor(255, 80, 70, 60))
        hl.setColorAt(1.0, QColor(255, 80, 70, 0))
        p.fillRect(QRectF(0, hz - 2, W, 8), QBrush(hl))

        # overhanging branches, swaying
        for pm, anchor, pivot, sign in self._branches:
            p.save()
            p.translate(anchor + pivot)
            p.rotate(sign * (1.2 * math.sin(t * 0.45) + 0.5 * math.sin(t * 1.1)))
            p.translate(-pivot)
            p.drawPixmap(0, 0, pm)
            p.restore()
