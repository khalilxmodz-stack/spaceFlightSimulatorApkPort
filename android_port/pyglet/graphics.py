from array import array

from . import _renderer


class Group:
    def __init__(self, order=0, parent=None):
        self.order = order
        self.parent = parent
        self.visible = True

    def _is_visible(self):
        g = self
        while g is not None:
            if not g.visible:
                return False
            g = g.parent
        return True


def group_visible(group):
    return group is None or group._is_visible()


class Batch:
    """Collects drawables; draw() emits them ordered by group.order (stable)."""

    def __init__(self):
        self._items = []

    def _add(self, item):
        self._items.append(item)

    def _remove(self, item):
        try:
            self._items.remove(item)
        except ValueError:
            pass

    def draw(self):
        items = [i for i in self._items if i._visible and group_visible(i._group)]
        items.sort(key=lambda i: i._group.order if i._group is not None else 0)
        for item in items:
            item._emit()


class VertexList:
    """What program.vertex_list(...) returns (used for the atmosphere rings)."""

    def __init__(self, count, mode, batch, group, position, colors):
        self._visible = True
        self._group = group
        self._batch = batch
        self._mode = mode
        self._position = list(position[1])
        self._colors = list(colors[1]) if colors else None
        self._cache = None
        if batch is not None:
            batch._add(self)

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        self._position = list(value)
        self._cache = None

    @property
    def colors(self):
        return self._colors

    @colors.setter
    def colors(self, value):
        self._colors = list(value)
        self._cache = None

    def _build(self):
        pos, col = self._position, self._colors
        n = len(pos) // 2

        def vert(i):
            if col:
                c = col[i * 4:i * 4 + 4]
                rgba = (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, c[3] / 255.0)
            else:
                rgba = (1.0, 1.0, 1.0, 1.0)
            return (pos[2 * i], pos[2 * i + 1]) + rgba

        out = array("f")
        if self._mode == 5:  # GL_TRIANGLE_STRIP
            for i in range(n - 2):
                for k in (i, i + 1, i + 2):
                    out.extend(vert(k))
        else:  # GL_TRIANGLES
            for i in range(n - n % 3):
                out.extend(vert(i))
        return out

    def _emit(self):
        if self._cache is None:
            self._cache = self._build()
        _renderer.add_mesh(self._cache)

    def draw(self, mode=None):
        if self._visible:
            self._emit()

    def delete(self):
        if self._batch is not None:
            self._batch._remove(self)
            self._batch = None
