"""Headless smoke test: runs the unmodified Game.py on the pyglet shim (no Kivy needed).

Run from the project root:  python tests/test_headless.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "android_port"))
sys.path.insert(1, ROOT)

import pyglet  # the shim
from pyglet import _renderer
from pyglet.window import key

import Game

assert pyglet.version.endswith("kivy-shim"), "real pyglet was imported instead of the shim"
W = Game.window


def frame(dt=1 / 60, ticks=1):
    for _ in range(ticks):
        pyglet.clock.tick(dt)
    W.dispatch_event("on_draw")
    meshes = [o for o in _renderer.ops if o[0] == "mesh"]
    labels = [o for o in _renderer.ops if o[0] == "label"]
    return sum(len(m[2]) // 6 for m in meshes), len(labels)


def press(sym):
    W.dispatch_event("on_key_press", sym, 0)


def release(sym):
    W.dispatch_event("on_key_release", sym, 0)


# --- main menu -----------------------------------------------------------------
verts, labels = frame()
print("menu: vertices=%d labels=%d" % (verts, labels))
assert verts > 100 and labels >= 3, "menu should draw stars, buttons and texts"

play = Game.main_menu.buttons[0]
W.dispatch_event("on_mouse_press", play.x + 5, play.y + 5, 1, 0)
assert Game.game_state == "PLAYING", "tapping Play must start the game"

# --- tutorial question modal: answer "No" -------------------------------------------
verts, labels = frame()
print("playing (first frame): vertices=%d labels=%d" % (verts, labels))
assert verts > 1000
for _ in range(3):
    frame()
if Game.tutorial_ask_modal.visible:
    no_btn = Game.tutorial_ask_modal.buttons[1]
    W.dispatch_event("on_mouse_press", no_btn.x + 5, no_btn.y + 5, 1, 0)
    assert not Game.tutorial_ask_modal.visible

# --- launch ---------------------------------------------------------------------------
press(key.SPACE)
release(key.SPACE)
print("engine engaged:", Game.rocket.engaged)
y0 = Game.rocket.velocity_y
for i in range(300):
    frame(1 / 30)
print("after 300 frames: fuel=%.0f speed=%.1f" % (Game.rocket.fuel, Game.rocket.speed))
assert Game.rocket.engaged and Game.rocket.speed > 5, "rocket should be accelerating"

# trajectory lines, zoom, warp, stage, pause, cheat menu
for sym in (key.PERIOD, key.PERIOD, key.COMMA, key.ENTER, key.P, key.M):
    press(sym)
    release(sym)
    frame()
W.dispatch_event("on_mouse_scroll", 0, 0, 0, -3)
W.dispatch_event("on_mouse_scroll", 0, 0, 0, 5)
press(key.LEFT)
for _ in range(20):
    frame()
release(key.LEFT)
Game.update_trajectory(0)
verts, labels = frame()
print("flight with trajectory: vertices=%d labels=%d" % (verts, labels))

press(key.C)                       # cheat menu
frame()
press(key.C)
press(key.ESCAPE)
frame()
press(key.ESCAPE)                  # pause on / off
frame()
print("OK - Game.py ran on the shim without errors")
