"""pyglet.shapes look-alikes that only record triangles for the Kivy backend.

Coordinate model copied from pyglet 2.1 (this is what the game relies on):
  * x / y only move the shape (a translation); they never rebuild the vertices.
  * x2/y2/x3/y3 are stored as absolute values, and whenever one of them (or a
    size / radius) is set, the vertices are rebuilt relative to the *current*
    x, y.
  * rotation is in degrees, clockwise, around (x, y) + anchor.
"""
from array import array
from math import cos, pi, radians, sin, sqrt

from . import _renderer
from .graphics import VertexList


def _rgba(color):
    c = tuple(color)
    return c + (255,) * (4 - len(c)) if len(c) < 4 else c[:4]


class ShapeBase:
    def __init__(self, x, y, color, batch, group):
        self._shx = float(x)
        self._shy = float(y)
        self._shcolor = _rgba(color)
        self._shrot = 0.0
        self._shax = 0.0
        self._shay = 0.0
        self._visible = True
        self._batch = batch
        self._group = group
        self._shlocal = None   # flat list [x0, y0, x1, y1, ...] of triangles, relative to (x, y)
        self._shcache = None   # array('f') world-space result
        if batch is not None:
            batch._add(self)

    # -- subclasses implement this --------------------------------------
    def _build_local(self):
        return []

    # -- invalidation ----------------------------------------------------
    def _geometry_changed(self):
        self._shlocal = None
        self._shcache = None

    def _world_changed(self):
        self._shcache = None

    # -- world-space mesh --------------------------------------------------
    def _mesh(self):
        if self._shcache is None:
            if self._shlocal is None:
                self._shlocal = self._build_local()
            loc = self._shlocal
            r, g, b, a = (c / 255.0 for c in self._shcolor)
            cx, cy, ax, ay = self._shx, self._shy, self._shax, self._shay
            out = array("f")
            ext = out.extend
            if self._shrot:
                th = -radians(self._shrot)
                co, si = cos(th), sin(th)
                for i in range(0, len(loc), 2):
                    dx, dy = loc[i] - ax, loc[i + 1] - ay
                    ext((cx + dx * co - dy * si, cy + dx * si + dy * co, r, g, b, a))
            else:
                ox, oy = cx - ax, cy - ay
                for i in range(0, len(loc), 2):
                    ext((ox + loc[i], oy + loc[i + 1], r, g, b, a))
            self._shcache = out
        return self._shcache

    def _emit(self):
        _renderer.add_mesh(self._mesh())

    def draw(self):
        if self._visible:
            self._emit()

    def delete(self):
        if self._batch is not None:
            self._batch._remove(self)
            self._batch = None

    # -- common properties ---------------------------------------------------
    @property
    def x(self):
        return self._shx

    @x.setter
    def x(self, v):
        self._shx = float(v)
        self._world_changed()

    @property
    def y(self):
        return self._shy

    @y.setter
    def y(self, v):
        self._shy = float(v)
        self._world_changed()

    @property
    def position(self):
        return (self._shx, self._shy)

    @position.setter
    def position(self, v):
        self._shx, self._shy = float(v[0]), float(v[1])
        self._world_changed()

    @property
    def rotation(self):
        return self._shrot

    @rotation.setter
    def rotation(self, v):
        self._shrot = float(v)
        self._world_changed()

    @property
    def anchor_x(self):
        return self._shax

    @anchor_x.setter
    def anchor_x(self, v):
        self._shax = float(v)
        self._world_changed()

    @property
    def anchor_y(self):
        return self._shay

    @anchor_y.setter
    def anchor_y(self, v):
        self._shay = float(v)
        self._world_changed()

    @property
    def color(self):
        return self._shcolor

    @color.setter
    def color(self, v):
        c = tuple(v)
        self._shcolor = c[:3] + ((c[3],) if len(c) > 3 else (self._shcolor[3],))
        self._world_changed()

    @property
    def opacity(self):
        return self._shcolor[3]

    @opacity.setter
    def opacity(self, v):
        self._shcolor = self._shcolor[:3] + (v,)
        self._world_changed()

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, v):
        self._visible = bool(v)

    @property
    def batch(self):
        return self._batch

    @property
    def group(self):
        return self._group


class Triangle(ShapeBase):
    def __init__(self, x, y, x2, y2, x3, y3, color=(255, 255, 255, 255),
                 blend_src=None, blend_dest=None, batch=None, group=None, program=None):
        super().__init__(x, y, color, batch, group)
        self._shx2, self._shy2, self._shx3, self._shy3 = map(float, (x2, y2, x3, y3))

    def _build_local(self):
        return [0.0, 0.0,
                self._shx2 - self._shx, self._shy2 - self._shy,
                self._shx3 - self._shx, self._shy3 - self._shy]

    def _setv(self, name, v):
        setattr(self, name, float(v))
        self._geometry_changed()

    x2 = property(lambda s: s._shx2, lambda s, v: s._setv("_shx2", v))
    y2 = property(lambda s: s._shy2, lambda s, v: s._setv("_shy2", v))
    x3 = property(lambda s: s._shx3, lambda s, v: s._setv("_shx3", v))
    y3 = property(lambda s: s._shy3, lambda s, v: s._setv("_shy3", v))


class Line(ShapeBase):
    def __init__(self, x, y, x2, y2, thickness=1.0, color=(255, 255, 255, 255),
                 blend_src=None, blend_dest=None, batch=None, group=None, program=None):
        super().__init__(x, y, color, batch, group)
        self._shx2, self._shy2 = float(x2), float(y2)
        self._shthick = float(thickness)

    def _build_local(self):
        dx, dy = self._shx2 - self._shx, self._shy2 - self._shy
        length = sqrt(dx * dx + dy * dy)
        if length == 0 or self._shthick <= 0:
            return []
        h = self._shthick / 2.0
        nx, ny = -dy / length * h, dx / length * h
        p0, p1 = (nx, ny), (-nx, -ny)
        p2, p3 = (dx + nx, dy + ny), (dx - nx, dy - ny)
        return [*p0, *p1, *p2, *p1, *p3, *p2]

    def _setv(self, name, v):
        setattr(self, name, float(v))
        self._geometry_changed()

    x2 = property(lambda s: s._shx2, lambda s, v: s._setv("_shx2", v))
    y2 = property(lambda s: s._shy2, lambda s, v: s._setv("_shy2", v))
    thickness = property(lambda s: s._shthick, lambda s, v: s._setv("_shthick", v))


class Rectangle(ShapeBase):
    def __init__(self, x, y, width, height, color=(255, 255, 255, 255),
                 blend_src=None, blend_dest=None, batch=None, group=None, program=None):
        super().__init__(x, y, color, batch, group)
        self._shw, self._shh = float(width), float(height)

    def _build_local(self):
        w, h = self._shw, self._shh
        return [0.0, 0.0, w, 0.0, w, h, 0.0, 0.0, w, h, 0.0, h]

    def _setv(self, name, v):
        setattr(self, name, float(v))
        self._geometry_changed()

    width = property(lambda s: s._shw, lambda s, v: s._setv("_shw", v))
    height = property(lambda s: s._shh, lambda s, v: s._setv("_shh", v))


class Circle(ShapeBase):
    def __init__(self, x, y, radius, segments=None, color=(255, 255, 255, 255),
                 blend_src=None, blend_dest=None, batch=None, group=None, program=None):
        super().__init__(x, y, color, batch, group)
        self._shrad = float(radius)
        # pyglet picks the segment count once, from the radius given at creation.
        self._shseg = int(segments) if segments else max(14, int(radius / 1.25))

    def _build_local(self):
        n, r = self._shseg, self._shrad
        out = []
        px, py = r, 0.0
        for i in range(1, n + 1):
            a = 2 * pi * i / n
            qx, qy = r * cos(a), r * sin(a)
            out += [0.0, 0.0, px, py, qx, qy]
            px, py = qx, qy
        return out

    @property
    def radius(self):
        return self._shrad

    @radius.setter
    def radius(self, v):
        self._shrad = float(v)
        self._geometry_changed()


class Arc(ShapeBase):
    """Circle outline drawn as a thin ring (no overlap between segments)."""

    def __init__(self, x, y, radius, segments=None, angle=2 * pi, start_angle=0,
                 closed=False, thickness=1.0, color=(255, 255, 255, 255),
                 blend_src=None, blend_dest=None, batch=None, group=None, program=None):
        super().__init__(x, y, color, batch, group)
        self._shrad = float(radius)
        self._shseg = int(segments) if segments else max(14, int(radius / 1.25))
        self._shangle = float(angle)
        self._shstart = float(start_angle)
        self._shthick = float(thickness)

    def _build_local(self):
        n = self._shseg
        r0, r1 = self._shrad - self._shthick / 2.0, self._shrad + self._shthick / 2.0
        out = []
        a = self._shstart
        ix, iy, ox, oy = r0 * cos(a), r0 * sin(a), r1 * cos(a), r1 * sin(a)
        for i in range(1, n + 1):
            a = self._shstart + self._shangle * i / n
            jx, jy, px, py = r0 * cos(a), r0 * sin(a), r1 * cos(a), r1 * sin(a)
            out += [ix, iy, ox, oy, px, py, ix, iy, px, py, jx, jy]
            ix, iy, ox, oy = jx, jy, px, py
        return out

    def _setv(self, name, v):
        setattr(self, name, float(v))
        self._geometry_changed()

    radius = property(lambda s: s._shrad, lambda s, v: s._setv("_shrad", v))
    thickness = property(lambda s: s._shthick, lambda s, v: s._setv("_shthick", v))


class _DefaultShader:
    """Stands in for the program returned by get_default_shader()."""

    def vertex_list(self, count, mode, batch=None, group=None, **attributes):
        return VertexList(count, mode, batch, group,
                          attributes["position"], attributes.get("colors"))


_shader = _DefaultShader()


def get_default_shader():
    return _shader
