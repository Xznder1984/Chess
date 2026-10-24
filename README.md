# Chess

Offline chess in Python with five computer levels. The rules engine, pieces and AI have no UI
dependency, so the same code can sit behind Kivy (included), or any other front end.

## Files

| File | Job |
|---|---|
| `pieces.py` | The pieces (characters): kinds, colours, glyphs, values, movement tables |
| `board.py` | Position, legal moves, castling, en passant, promotion, check, draws, FEN, move notation |
| `ai.py` | Difficulty levels, evaluation, alpha-beta search, optional Stockfish |
| `game.py` | Game controller: selection, moves, undo, computer turns on a worker thread |
| `main.py` | Kivy screen: board, new-game dialog, promotion dialog, keyboard play |
| `theme.py`, `contrast_check.py` | Colours and the WCAG contrast check for every colour pair |
| `test_engine.py` | Perft counts for 5 reference positions, notation, draws, all AI levels, game flow |

## Run

    pip install -r requirements.txt
    python main.py

Tap or click a piece, then a highlighted square. Dots mark moves, rings mark captures.
Keyboard: arrows move the cursor, Enter or Space selects, Esc cancels, U undo, N new game, F flip board.

## Difficulty levels

| Level | How it plays |
|---|---|
| Baby | Random legal moves |
| Easy | One move ahead with noise, and about 1 move in 8 is random |
| Normal | Searches 3 moves ahead |
| Hard | Searches up to 6 moves ahead, 5 seconds per move |
| Grandmaster | Stockfish tuned to a 2850 Elo target when selected; otherwise the strongest built-in setting |

Grandmaster is tuned for a very strong challenge near Magnus Carlsen's playing strength, without
claiming to copy his personal style or reproduce his games. When selected, Stockfish uses its 2850
Elo strength target and thinks for up to 12 seconds per move. This target is approximate and varies
with hardware and time control. The new-game dialog lets you choose Stockfish or the built-in engine;
the installers bundle Stockfish, so no separate setup or game-time download is needed. The built-in
engine is much weaker, and the screen says which engine is selected or available. Stockfish 19 is
GPLv3; packages include its license and [corresponding source](https://github.com/official-stockfish/Stockfish/tree/sf_19).

## Build

Tagged releases provide separate desktop installers and an Android APK: Windows setup, macOS disk
images for Intel and Apple Silicon, Linux `.deb` and portable archive, and `Chess-Android-arm64.apk`.
The desktop installers install the game together with its matching Stockfish engine inside the app
folder. Android is built and uploaded as a separate APK job. GitHub Actions builds each desktop
version on its matching runner; Android is built on Linux. These release packages have not been
built locally on every platform.
Create and push a version tag such as `v1.0.0` to run the release workflow. You can also run the
workflow manually to check build artifacts without publishing a release.

For local builds, build on the target platform. PyInstaller and Buildozer do not cross-compile.

- **Windows:** `pip install pyinstaller` then `pyinstaller --windowed --manifest windows.manifest --name Chess main.py`
- **macOS:** the same command on a Mac. It builds for that Mac's chip (Intel or Apple Silicon).
  Unsigned apps trigger a Gatekeeper warning until you sign and notarize them.
- **Linux:** the same command.
- **Android:** `pip install buildozer`, then `buildozer android debug` on Linux, macOS or WSL.
  Edit `package.domain` in `buildozer.spec` first.
- **iOS:** use kivy-ios on a Mac with Xcode and an Apple developer account.

If PyInstaller misses Kivy files, follow the Kivy PyInstaller guide for your Kivy version.

## Accessibility

`python contrast_check.py` checks every pair. Text is at least 4.5:1, piece outlines, move dots and
capture rings are at least 3:1 on every square colour. White pieces have a black outline because a
white fill alone is only 1.24:1 on a light square. Meaning never depends on colour alone: the
status line states check, mate and draws in words, markers are shapes, and moves are listed as text.

## Privacy and licences

The game is offline. It has no accounts, analytics, ads, network calls or web embeds, so a cookie
banner, privacy policy and refund policy do not apply. Add them only if you publish a store listing
that requires them. Kivy is MIT licensed. Pieces are drawn with DejaVu Sans glyphs, a font that ships
inside Kivy under a free licence. No images are used.
