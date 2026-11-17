"""Android / Kivy entry point for Skypiercer (used by Buildozer).

The desktop version is unchanged: run `python Game.py` with pyglet installed.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)  # Game.py opens constants.json and assets/ with relative paths

# android_port/ contains a small pyglet-compatible layer; putting it first makes
# `import pyglet` inside Game.py / Body.py / Rocket.py resolve to it.
sys.path.insert(0, os.path.join(HERE, "android_port"))
sys.path.insert(1, HERE)

from kivy.config import Config  # noqa: E402

Config.set("kivy", "exit_on_escape", "0")
Config.set("graphics", "maxfps", "60")
Config.set("input", "mouse", "mouse,disable_multitouch")

from kivy_backend import SkypiercerApp  # noqa: E402

if __name__ == "__main__":
    SkypiercerApp().run()
