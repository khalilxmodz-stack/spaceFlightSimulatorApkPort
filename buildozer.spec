[app]
title = Skypiercer
package.name = skypiercer
package.domain = org.skypiercer

source.dir = .
source.include_exts = py,ttf,json
source.exclude_dirs = tests, img, .github, .git, bin, .buildozer, __pycache__, venv, .venv
source.exclude_patterns = *.png, README*, requirements.txt

version = 0.1.0

# Game.py needs Python >= 3.10 (match statements); python-for-android ships 3.11.
requirements = python3,kivy==2.3.0

orientation = landscape
fullscreen = 1

android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 0
