from . import _renderer


def add_file(path):
    """Remember a font file; the Kivy backend registers it when it first needs it."""
    _renderer.font_files.append(path)
