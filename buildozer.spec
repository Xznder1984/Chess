[app]
title = ChessPy
package.name = chesspy
# Change the domain to one you own before publishing.
package.domain = org.pychess
source.dir = .
source.include_exts = py
source.include_exts = py,kv,atlas,png,jpg,ttf,stockfish,bin,txt
source.exclude_patterns = test_engine.py,contrast_check.py,.github/*,stockfish-extracted/*
version = 1.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
