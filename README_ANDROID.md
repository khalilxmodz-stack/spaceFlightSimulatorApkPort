# Skypiercer on Android

`Game.py`, `Body.py` and `Rocket.py` are **unchanged**. For Android they run on top of
`android_port/pyglet` (a small pyglet-compatible layer) and `android_port/kivy_backend.py`
(Kivy rendering, touch input, on-screen buttons). The desktop version still works with
the real pyglet: `python Game.py`.

## Getting the APK (phone only)
1. Put all files in a GitHub repository (branch `main`).
   The workflow must be at `.github/workflows/android.yml`. If your file manager hides
   `.github`, create that file on github.com ("Add file" -> "Create new file") and paste
   the contents of `android.yml`.
2. Open the **Actions** tab -> **Build Android APK** (it starts on every push, or press
   *Run workflow*). The first build takes ~25-40 minutes, later ones are faster (cache).
3. When it is green, open the run -> **Artifacts** -> `skypiercer-apk`, download, unzip,
   install the `.apk` (allow "install unknown apps").
4. If a step is red: open it and send the last ~100 lines of its log.

## Touch controls
Left: ROT LEFT/RIGHT, THR -/+ (throttle), PAUSE, CHEAT. Right: ENGINE, STAGE, WARP -/+,
ZOOM -/+, CHUTE, RESET ZOOM. Pinch with two fingers to zoom. Tap menu/modals like a mouse.
The Android back button = pause. Typing into the cheat menu needs a hardware keyboard.

## Checking the game logic without a phone
`python tests/test_headless.py` runs the real game (menu -> launch -> flight) headlessly.
