from . import _renderer


def run():
    if _renderer.run_hook is None:
        raise RuntimeError("No backend registered (start the game through main.py).")
    _renderer.run_hook()


def exit():
    if _renderer.exit_hook is not None:
        _renderer.exit_hook()
