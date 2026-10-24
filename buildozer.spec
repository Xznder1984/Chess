[app]
title = ChessPy
package.name = chesspy
# Change the domain to one you own before publishing.
package.domain = org.pychess
source.dir = .
source.include_exts = py,kv,atlas,png,jpg,ttf,stockfish,bin,txt
source.exclude_patterns = test_engine.py,contrast_check.py,.github/*,stockfish-extracted/*
version = 1.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0
android.archs = arm64-v8a
p4a.branch = develop
p4a.commit = 9fac8b4ed23c3a30050dc5e260568cf4eee13ace

[buildozer]
log_level = 2
warn_on_root = 1
