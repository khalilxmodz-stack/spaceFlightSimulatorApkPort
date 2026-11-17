"""Minimal pyglet-compatible layer used by the Android (Kivy) build of Skypiercer.

Only the parts of pyglet that Skypiercer uses are implemented.  Drawing is
recorded into a frame list (see _renderer.py) and replayed by kivy_backend.py.
"""
from . import _renderer  # noqa: F401
from . import event, gl, font, math, clock, app, graphics, shapes, text, window  # noqa: F401

version = "2.1-kivy-shim"
