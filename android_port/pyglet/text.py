from . import _renderer


def _rgba(color):
    c = tuple(color)
    return c + (255,) * (4 - len(c)) if len(c) < 4 else c[:4]


class Label:
    def __init__(self, text="", x=0, y=0, z=0, width=None, height=None,
                 anchor_x="left", anchor_y="baseline", rotation=0, multiline=False,
                 dpi=None, font_name=None, font_size=None, weight=None, bold=False,
                 italic=False, stretch=False, color=(255, 255, 255, 255), align="left",
                 batch=None, group=None, **_ignored):
        self.text = text
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.anchor_x = anchor_x
        self.anchor_y = anchor_y
        self.multiline = multiline
        self.font_name = font_name
        self.font_size = font_size if font_size else 12
        self._color = _rgba(color)
        self._visible = True
        self._batch = batch
        self._group = group
        if batch is not None:
            batch._add(self)

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value):
        self._color = _rgba(value)

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = bool(value)

    @property
    def batch(self):
        return self._batch

    def _emit(self):
        if self.text:
            _renderer.add_label(self)

    def draw(self):
        if self._visible:
            self._emit()

    def delete(self):
        if self._batch is not None:
            self._batch._remove(self)
            self._batch = None
