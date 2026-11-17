from .. import _renderer
from ..math import Mat4
from . import key  # noqa: F401  (pyglet.window.key)


class Window:
    """A logical window.  The Kivy backend maps it onto the real screen."""

    def __init__(self, width=640, height=480, caption=None, resizable=False, **_ignored):
        self.width = width
        self.height = height
        self.caption = caption
        self.view = Mat4()
        self.projection = Mat4()
        self._handlers = {}
        self._pushed = []
        _renderer.window = self

    def event(self, arg=None):
        """@window.event  or  @window.event('name')."""
        if callable(arg):
            self._handlers[arg.__name__] = arg
            return arg

        def deco(fn):
            self._handlers[arg or fn.__name__] = fn
            return fn
        return deco

    def push_handlers(self, *objs, **named):
        for o in objs:
            self._pushed.append(o)
        for name, fn in named.items():
            self._handlers[name] = fn

    def dispatch_event(self, name, *args):
        for obj in reversed(self._pushed):
            fn = getattr(obj, name, None)
            if fn is not None and fn(*args):
                return True
        fn = self._handlers.get(name)
        if fn is not None and fn(*args):
            return True
        return False

    def clear(self):
        _renderer.begin_frame()

    def set_caption(self, caption):
        self.caption = caption

    def close(self):
        from .. import app
        app.exit()
