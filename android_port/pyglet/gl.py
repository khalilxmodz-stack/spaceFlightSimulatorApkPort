"""Tiny stand-in for pyglet.gl: only the names Skypiercer uses."""
from . import _renderer

GL_TRIANGLES = 4
GL_TRIANGLE_STRIP = 5


def glClearColor(r, g, b, a):
    _renderer.clear_color = (r, g, b, a)
