"""Kivy front-end for Skypiercer.

Game.py is used unchanged.  It talks to the small `pyglet` look-alike in
android_port/pyglet, which only *records* what to draw.  This file replays that
recording with Kivy, scales the fixed 1024x768 game screen to the phone (with
black bars), and turns touches into the mouse / keyboard events the game
expects.
"""
import math
import traceback

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.text import LabelBase
from kivy.core.window import Window as KivyWindow
from kivy.graphics import Color, Mesh, Rectangle, RenderContext
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import pyglet  # the shim (main.py puts android_port first on sys.path)
from pyglet import _renderer
from pyglet.window import key as K

# ---------------------------------------------------------------------------
# GPU side: one custom shader that takes per-vertex colour and applies the
# game's 2D "view" transform (camera) + the screen scaling in one affine step.
# ---------------------------------------------------------------------------
VERTEX_SHADER = """
$HEADER$
attribute vec4 vColor;
uniform vec4 view_abcd;
uniform vec2 view_txy;
varying vec4 v_color;
void main(void) {
    vec2 p = vec2(view_abcd.x * vPosition.x + view_abcd.z * vPosition.y + view_txy.x,
                  view_abcd.y * vPosition.x + view_abcd.w * vPosition.y + view_txy.y);
    v_color = vColor;
    gl_Position = projection_mat * vec4(p, 0.0, 1.0);
}
"""

FRAGMENT_SHADER = """
$HEADER$
varying vec4 v_color;
void main(void) {
    gl_FragColor = v_color;
}
"""

VERTEX_FORMAT = [(b"vPosition", 2, "float"), (b"vColor", 4, "float")]
MAX_VERTS_PER_MESH = 65535          # Kivy mesh indices are unsigned 16-bit
INDEX_LIST = list(range(MAX_VERTS_PER_MESH))


class MeshSlot:
    """A reusable (RenderContext, Mesh) pair, so no shader is built per frame."""

    def __init__(self):
        self.rc = RenderContext(use_parent_projection=True)
        self.rc.shader.vs = VERTEX_SHADER
        self.rc.shader.fs = FRAGMENT_SHADER
        self.mesh = None

    def set(self, vertices, count, aff):
        a, b, c, d, tx, ty = aff
        self.rc["view_abcd"] = (a, b, c, d)
        self.rc["view_txy"] = (tx, ty)
        if self.mesh is None:
            with self.rc:
                self.mesh = Mesh(fmt=VERTEX_FORMAT, mode="triangles",
                                 vertices=vertices, indices=INDEX_LIST[:count])
        else:
            self.mesh.vertices = vertices
            self.mesh.indices = INDEX_LIST[:count]


# ---------------------------------------------------------------------------
# The view that shows the game
# ---------------------------------------------------------------------------
class GameView(Widget):
    def __init__(self, game, **kwargs):
        super().__init__(**kwargs)
        self.game = game
        self.win = game.window
        self.slots = []
        self.tex_cache = {}
        self.fonts = set()
        self.touches = {}
        self.pinch_dist = None
        self.s = 1.0
        self.ox = self.oy = 0.0
        self.bind(size=self._layout, pos=self._layout)
        self._layout()

    # -- screen <-> game coordinates ----------------------------------------
    def _layout(self, *_):
        lw, lh = self.win.width, self.win.height
        self.s = min(self.width / lw, self.height / lh) or 1.0
        self.ox = self.x + (self.width - lw * self.s) / 2.0
        self.oy = self.y + (self.height - lh * self.s) / 2.0

    def to_game(self, x, y):
        return (x - self.ox) / self.s, (y - self.oy) / self.s

    def inside_game(self, gx, gy):
        return 0 <= gx <= self.win.width and 0 <= gy <= self.win.height

    # -- text -------------------------------------------------------------------
    def _font_for(self, name):
        if not name:
            return None
        if name not in self.fonts:
            if _renderer.font_files:
                try:
                    LabelBase.register(name=name, fn_regular=_renderer.font_files[0])
                    self.fonts.add(name)
                except Exception:
                    Logger.exception("Skypiercer: could not register font")
                    return None
            else:
                return None
        return name

    def _texture(self, text, font_name, px, width_px, multiline):
        key = (text, font_name, px, width_px if multiline else None)
        tex = self.tex_cache.pop(key, None)
        if tex is None:
            kw = {"text": text, "font_size": px, "color": (1, 1, 1, 1)}
            font = self._font_for(font_name)
            if font:
                kw["font_name"] = font
            if multiline and width_px:
                kw["text_size"] = (width_px, None)
                kw["halign"] = "left"
            core = CoreLabel(**kw)
            core.refresh()
            tex = core.texture
        self.tex_cache[key] = tex            # re-insert = most recently used
        while len(self.tex_cache) > 300:
            self.tex_cache.pop(next(iter(self.tex_cache)))
        return tex

    # -- one frame ------------------------------------------------------------------
    def render(self):
        s, ox, oy = self.s, self.ox, self.oy
        canvas = self.canvas
        canvas.clear()
        canvas.add(Color(0, 0, 0, 1))
        canvas.add(Rectangle(pos=self.pos, size=self.size))

        used = 0
        for op in _renderer.ops:
            kind, aff = op[0], op[1]
            a, b, c, d, tx, ty = aff
            if kind == "mesh":
                screen_aff = (s * a, s * b, s * c, s * d, ox + s * tx, oy + s * ty)
                data, total = op[2], len(op[2]) // 6
                for start in range(0, total, MAX_VERTS_PER_MESH):
                    n = min(MAX_VERTS_PER_MESH, total - start)
                    if used == len(self.slots):
                        self.slots.append(MeshSlot())
                    slot = self.slots[used]
                    used += 1
                    slot.set(data[start * 6:(start + n) * 6].tolist(), n, screen_aff)
                    canvas.add(slot.rc)
            else:
                (text, font_name, size, rgba, x, y,
                 anchor_x, anchor_y, width, multiline) = op[2]
                px = max(4, int(round(size * s)))
                tex = self._texture(text, font_name, px, int((width or 0) * s), multiline)
                w, h = tex.size
                sx = ox + s * (a * x + c * y + tx)
                sy = oy + s * (b * x + d * y + ty)
                if anchor_x == "center":
                    sx -= w / 2.0
                elif anchor_x == "right":
                    sx -= w
                if anchor_y == "center":
                    sy -= h / 2.0
                elif anchor_y == "top":
                    sy -= h
                elif anchor_y == "baseline":
                    sy -= 0.22 * h
                canvas.add(Color(*rgba))
                canvas.add(Rectangle(texture=tex, pos=(round(sx), round(sy)), size=(w, h)))

        # black bars hide anything drawn outside the 4:3 game area
        canvas.add(Color(0, 0, 0, 1))
        gx0, gy0 = ox, oy
        gx1, gy1 = ox + self.win.width * s, oy + self.win.height * s
        right, top = self.x + self.width, self.y + self.height
        if gx0 > self.x:
            canvas.add(Rectangle(pos=(self.x, self.y), size=(gx0 - self.x, self.height)))
            canvas.add(Rectangle(pos=(gx1, self.y), size=(right - gx1, self.height)))
        if gy0 > self.y:
            canvas.add(Rectangle(pos=(self.x, self.y), size=(self.width, gy0 - self.y)))
            canvas.add(Rectangle(pos=(self.x, gy1), size=(self.width, top - gy1)))

    # -- touch: tap = mouse click, pinch = scroll wheel ----------------------------------------
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        self.touches[touch.uid] = touch.pos
        if len(self.touches) == 2:
            self.pinch_dist = self._distance()
        elif len(self.touches) == 1:
            gx, gy = self.to_game(*touch.pos)
            if self.inside_game(gx, gy):
                self.win.dispatch_event("on_mouse_motion", gx, gy, 0, 0)
                self.win.dispatch_event("on_mouse_press", gx, gy, 1, 0)
        return True

    def on_touch_move(self, touch):
        if touch.uid not in self.touches:
            return False
        self.touches[touch.uid] = touch.pos
        if len(self.touches) == 2 and self.pinch_dist:
            dist = self._distance()
            if dist > 0:
                ticks = math.log(dist / self.pinch_dist) / math.log(1.1)
                self.pinch_dist = dist
                cx, cy = self.to_game(*self._centre())
                self.win.dispatch_event("on_mouse_scroll", cx, cy, 0, ticks)
        return True

    def on_touch_up(self, touch):
        if touch.uid in self.touches:
            del self.touches[touch.uid]
            self.pinch_dist = None
            return True
        return False

    def _distance(self):
        (x1, y1), (x2, y2) = list(self.touches.values())[:2]
        return math.hypot(x2 - x1, y2 - y1)

    def _centre(self):
        (x1, y1), (x2, y2) = list(self.touches.values())[:2]
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0


# ---------------------------------------------------------------------------
# On-screen buttons that behave like keyboard keys
# ---------------------------------------------------------------------------
class KeyButton(Widget):
    """Held = key held.  `scroll` buttons zoom instead (like the mouse wheel)."""

    def __init__(self, text, symbol=None, scroll=0.0, backend=None, **kwargs):
        super().__init__(**kwargs)
        self.symbol, self.scroll, self.backend = symbol, scroll, backend
        self.pressed = False
        self._timer = None
        self.label = Label(text=text, bold=True, halign="center", valign="middle")
        self.add_widget(self.label)
        with self.canvas.before:
            self._color = Color(0.2, 0.3, 0.85, 0.40)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *_):
        self._rect.pos, self._rect.size = self.pos, self.size
        self.label.pos, self.label.size = self.pos, self.size
        self.label.text_size = self.size
        self.label.font_size = self.height * 0.28

    def _set_pressed(self, value):
        self.pressed = value
        self._color.rgba = (0.45, 0.6, 1.0, 0.75) if value else (0.2, 0.3, 0.85, 0.40)

    def on_touch_down(self, touch):
        if self.pressed or not self.collide_point(*touch.pos):
            return False
        touch.grab(self)
        self._set_pressed(True)
        if self.symbol is not None:
            self.backend.key_down(self.symbol)
        if self.scroll:
            self._timer = Clock.schedule_interval(self._scroll_tick, 1 / 30.0)
        return True

    def _scroll_tick(self, _dt):
        w = self.backend.game.window
        w.dispatch_event("on_mouse_scroll", w.width / 2, w.height / 2, 0, self.scroll)

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        self._set_pressed(False)
        if self.symbol is not None:
            self.backend.key_up(self.symbol)
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        return True


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------
class SkypiercerApp(App):
    title = "Skypiercer"

    def build(self):
        self.game = None
        self.view = None
        self.error_shown = False
        try:
            import Game  # runs the whole game setup (windows, rocket, menu, ...)
            self.game = Game
        except Exception:
            text = traceback.format_exc()
            Logger.error("Skypiercer: failed to load the game\n" + text)
            return Label(text="Skypiercer failed to start:\n\n" + text,
                         font_size="12sp", halign="left", valign="top",
                         text_size=KivyWindow.size)

        _renderer.exit_hook = self.stop
        _renderer.run_hook = lambda: None

        root = FloatLayout()
        self.view = GameView(Game, size_hint=(1, 1))
        root.add_widget(self.view)
        self.error_label = Label(text="", font_size="11sp", color=(1, 0.4, 0.4, 1),
                                 halign="left", valign="top", size_hint=(1, None),
                                 height=dp(120), pos_hint={"top": 1})
        self.error_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        self._add_controls(root)
        root.add_widget(self.error_label)

        KivyWindow.bind(on_keyboard=self._on_keyboard, on_key_up=self._on_key_up,
                        on_textinput=self._on_textinput)
        KivyWindow.bind(size=lambda *_: self._relayout())
        Clock.schedule_interval(self._frame, 1 / 60.0)
        return root

    def on_pause(self):
        return True  # keep the game alive when the app goes to the background

    # -- frame loop --------------------------------------------------------------------------------
    def _frame(self, dt):
        try:
            pyglet.clock.tick(dt)
            self.game.window.dispatch_event("on_draw")
            self.view.render()
        except Exception:
            text = traceback.format_exc()
            Logger.error("Skypiercer: frame error\n" + text)
            if not self.error_shown:
                self.error_shown = True
                self.error_label.text = text[-900:]

    # -- keys ------------------------------------------------------------------------------------------
    def key_down(self, symbol):
        self.game.window.dispatch_event("on_key_press", symbol, 0)

    def key_up(self, symbol):
        self.game.window.dispatch_event("on_key_release", symbol, 0)

    _SPECIAL = {13: K.ENTER, 271: K.ENTER, 27: K.ESCAPE, 8: K.BACKSPACE,
                276: K.LEFT, 273: K.UP, 275: K.RIGHT, 274: K.DOWN}

    def _map_key(self, code):
        if code in self._SPECIAL:
            return self._SPECIAL[code]
        if 32 <= code < 127:
            return code
        return None

    def _on_keyboard(self, _win, code, _scan, _text, _mods):
        # Hardware keyboard / Android back button (code 27 = back = pause)
        sym = self._map_key(code)
        if sym is None:
            return False
        self.key_down(sym)
        Clock.schedule_once(lambda _dt: self.key_up(sym), 0.05) if code == 27 else None
        return True

    def _on_key_up(self, _win, code, _scan, *_):
        sym = self._map_key(code)
        if sym is not None and code != 27:
            self.key_up(sym)

    def _on_textinput(self, _win, text):
        self.game.window.dispatch_event("on_text", text)

    # -- control layout ------------------------------------------------------------------------------
    def _add_controls(self, root):
        self.buttons = []

        def add(name, text, symbol=None, scroll=0.0):
            b = KeyButton(text, symbol, scroll, backend=self, size_hint=(None, None))
            self.buttons.append((name, b))
            root.add_widget(b)

        # left side: steering + throttle, plus pause / cheat at the top
        add("rot_l", "ROT\nLEFT", K.LEFT)
        add("rot_r", "ROT\nRIGHT", K.RIGHT)
        add("thr_d", "THR\n-", K.Q)
        add("thr_u", "THR\n+", K.E)
        add("pause", "PAUSE", K.ESCAPE)
        add("cheat", "CHEAT", K.C)
        # right side: engine, stage, warp, zoom, parachute, reset zoom
        add("engine", "ENGINE", K.SPACE)
        add("stage", "STAGE", K.ENTER)
        add("warp_d", "WARP\n-", K.COMMA)
        add("warp_u", "WARP\n+", K.PERIOD)
        add("zoom_o", "ZOOM\n-", None, -0.5)
        add("zoom_i", "ZOOM\n+", None, +0.5)
        add("chute", "CHUTE", K.P)
        add("map", "RESET\nZOOM", K.M)
        Clock.schedule_once(lambda _dt: self._relayout(), 0)

    def _relayout(self):
        W, H = KivyWindow.size
        pad = dp(8)
        u = min(dp(72), (H - 2 * pad) / 5.5)
        gap = u * 0.12
        for _, b in self.buttons:
            b.size = (u * 1.1, u)
        pos = {}
        # left column pair (bottom): rows from the bottom
        pos["rot_l"] = (pad, pad)
        pos["rot_r"] = (pad + u * 1.1 + gap, pad)
        pos["thr_d"] = (pad, pad + u + gap)
        pos["thr_u"] = (pad + u * 1.1 + gap, pad + u + gap)
        pos["pause"] = (pad, H - pad - u)
        pos["cheat"] = (pad, H - pad - 2 * u - gap)
        # right column pair
        xr1 = W - pad - u * 1.1
        xr0 = xr1 - u * 1.1 - gap
        pos["engine"], pos["stage"] = (xr0, pad), (xr1, pad)
        pos["warp_d"], pos["warp_u"] = (xr0, pad + u + gap), (xr1, pad + u + gap)
        pos["zoom_o"], pos["zoom_i"] = (xr0, pad + 2 * (u + gap)), (xr1, pad + 2 * (u + gap))
        pos["chute"], pos["map"] = (xr0, pad + 3 * (u + gap)), (xr1, pad + 3 * (u + gap))
        for name, b in self.buttons:
            b.pos = pos[name]
