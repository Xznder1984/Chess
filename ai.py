"""AI levels, built-in alpha-beta search, and optional full-strength Stockfish.

Grandmaster uses Stockfish's strongest playing setting when available. It does not
reproduce Magnus Carlsen's individual style; the built-in search is a weaker fallback.
"""

import gc
import os
import random
import shutil
import subprocess
import platform as host_platform
import sys
import threading
import time
from dataclasses import dataclass

from board import move_uci
from pieces import WHITE, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING, KING_MG, KING_EG

INF = 10 ** 9
MATE = 100000
MATE_LIMIT = MATE - 1000
EXACT, LOWER, UPPER = 0, 1, 2


@dataclass(frozen=True)
class Level:
    name: str
    description: str
    depth: int            # maximum search depth of the built-in engine
    seconds: float        # thinking time budget
    noise: int = 0        # centipawn noise added to each root move (0 = none)
    blunder: float = 0.0  # chance of playing a random legal move instead
    stockfish_elo: int = 0


LEVELS = (
    Level("Baby", "Plays random legal moves.", 0, 0.0, blunder=1.0),
    Level("Easy", "Looks one move ahead and often slips.", 1, 1.0, noise=150, blunder=0.12),
    Level("Normal", "Looks a few moves ahead and rarely blunders.", 3, 3.0),
    Level("Hard", "Searches deeper, up to 5 seconds per move.", 6, 5.0),
    Level("Grandmaster",
          "Stockfish targets 2850 Elo when selected. It plays in Carlsen's strength range, not his personal style.",
          40, 12.0, stockfish_elo=2850),
)
LEVEL_BY_NAME = {lv.name: lv for lv in LEVELS}


# ---------------------------------------------------------------- evaluation
def evaluate(board):
    """Static score in centipawns from the side to move's point of view.

    Material, piece-square scores and phase are maintained incrementally by Board,
    so this is a handful of arithmetic rather than a 64-square scan.
    """
    score = board.eval_score
    material = board.eval_material
    phase = min(board.eval_phase, 24)
    wk, bk = board.king_sq
    mg = KING_MG[wk] - KING_MG[bk ^ 56]
    eg = KING_EG[wk] - KING_EG[bk ^ 56]
    score += (mg * phase + eg * (24 - phase)) // 24
    score += 30 * (board.bishop_w >= 2) - 30 * (board.bishop_b >= 2)
    if phase <= 8 and abs(material) >= 400:              # help convert won endgames
        loser = bk if material > 0 else wk
        winner = wk if material > 0 else bk
        lr, lc = loser >> 3, loser & 7
        edge = (min(lr, 7 - lr) + min(lc, 7 - lc))       # 0 = edge, 6 = centre
        dist = abs(lr - (winner >> 3)) + abs(lc - (winner & 7))
        bonus = (6 - edge) * 10 + (14 - dist) * 4
        score += bonus if material > 0 else -bonus
    return score if board.turn == WHITE else -score


# ---------------------------------------------------------------- search
class _Stop(Exception):
    pass


class Search:
    def __init__(self, board, level, cancel, tt=None):
        self.board = board
        self.level = level
        self.cancel = cancel
        self.tt = tt if tt is not None else {}
        self.killers = [[None, None] for _ in range(128)]
        self.history = {}
        self.nodes = 0
        self.start = time.monotonic()
        self.deadline = self.start + level.seconds

    # -- helpers
    def _tick(self):
        self.nodes += 1
        if self.nodes & 511 == 0 and (time.monotonic() > self.deadline or self.cancel.is_set()):
            raise _Stop

    def _order(self, moves, tt_move, ply):
        if len(moves) < 2:
            return
        sq = self.board.squares
        k1, k2 = self.killers[ply]
        hist = self.history

        def score(m):
            if m == tt_move:
                return 10 ** 7
            victim = sq[m.to]
            mover = sq[m.frm]
            if victim is not None:
                return 10 ** 6 + victim.value * 16 - mover.kind
            if mover.kind == PAWN and (m.frm & 7) != (m.to & 7):
                return 10 ** 6 + 1600                      # en passant
            if m.promo:
                return 9 * 10 ** 5 + m.promo
            if m == k1:
                return 8 * 10 ** 5
            if m == k2:
                return 7 * 10 ** 5
            return hist.get((m.frm, m.to), 0)

        moves.sort(key=score, reverse=True)

    def _has_pieces(self):
        b = self.board
        for p in b.squares:
            if p is not None and p.color == b.turn and p.kind in (KNIGHT, BISHOP, ROOK, QUEEN):
                return True
        return False

    # -- quiescence
    def _quiesce(self, alpha, beta, ply):
        self._tick()
        b = self.board
        stand = evaluate(b)
        if ply >= 100 or stand >= beta:
            return stand
        if stand > alpha:
            alpha = stand
        moves = b.pseudo_moves(captures_only=True)
        self._order(moves, None, ply)
        me = b.turn
        for m in moves:
            victim = b.squares[m.to]
            if victim is not None and not m.promo and stand + victim.value + 200 < alpha:
                continue                                     # delta pruning
            b.push(m)
            if b.attacked(b.king_sq[me], b.turn):
                b.pop()
                continue
            score = -self._quiesce(-beta, -alpha, ply + 1)
            b.pop()
            if score >= beta:
                return score
            if score > alpha:
                alpha = score
        return alpha

    # -- main search
    def _negamax(self, depth, alpha, beta, ply, allow_null=True):
        self._tick()
        b = self.board
        if b.halfmove >= 100 or b.is_repetition():
            return 0
        in_check = b.in_check()
        if in_check:
            depth += 1
        if depth <= 0 or ply >= 100:
            return self._quiesce(alpha, beta, ply)

        alpha0, key = alpha, b.key
        tt_move = None
        entry = self.tt.get(key)
        if entry is not None:
            d, flag, s, tt_move = entry
            if d >= depth:
                s = s - ply if s > MATE_LIMIT else s + ply if s < -MATE_LIMIT else s
                if flag == EXACT or (flag == LOWER and s >= beta) or (flag == UPPER and s <= alpha):
                    return s

        if allow_null and not in_check and depth >= 3 and self._has_pieces():
            b.push_null()
            s = -self._negamax(depth - 3, -beta, -beta + 1, ply + 1, False)
            b.pop_null()
            if s >= beta:
                return beta

        moves = b.pseudo_moves()
        self._order(moves, tt_move, ply)
        me = b.turn
        best, best_move, legal = -INF, None, 0
        sq = b.squares
        for m in moves:
            quiet = sq[m.to] is None and not m.promo
            b.push(m)
            if b.attacked(b.king_sq[me], b.turn):
                b.pop()
                continue
            legal += 1
            reduced = legal > 4 and depth >= 3 and quiet and not in_check
            if legal == 1:
                s = -self._negamax(depth - 1, -beta, -alpha, ply + 1)
            else:
                if reduced:                                          # late move reduction
                    s = -self._negamax(depth - 2, -alpha - 1, -alpha, ply + 1)
                else:
                    s = -self._negamax(depth - 1, -alpha - 1, -alpha, ply + 1)
                if s > alpha and (reduced or s < beta):
                    s = -self._negamax(depth - 1, -beta, -alpha, ply + 1)
            b.pop()
            if s > best:
                best, best_move = s, m
            if s > alpha:
                alpha = s
                if alpha >= beta:
                    if quiet:
                        ks = self.killers[ply]
                        if ks[0] != m:
                            ks[1], ks[0] = ks[0], m
                        self.history[(m.frm, m.to)] = self.history.get((m.frm, m.to), 0) + depth * depth
                    break
        if legal == 0:
            return -MATE + ply if in_check else 0
        flag = UPPER if best <= alpha0 else LOWER if best >= beta else EXACT
        stored = best + ply if best > MATE_LIMIT else best - ply if best < -MATE_LIMIT else best
        if len(self.tt) > 300000:
            self.tt.clear()
        self.tt[key] = (depth, flag, stored, best_move)
        return best

    # -- root
    def run(self):
        b = self.board
        root = b.legal_moves()
        if not root:
            return None
        if len(root) == 1 or self.level.depth <= 0:
            return root[0]
        best = root[0]
        try:
            if self.level.noise:
                return self._noisy_root(root)
            for depth in range(1, self.level.depth + 1):
                iteration_start = time.monotonic()
                alpha, best_here, legal = -INF, None, 0
                self._order(root, root[0], 0)
                for m in root:
                    b.push(m)
                    if legal == 0:
                        s = -self._negamax(depth - 1, -INF, INF, 1)
                    else:                                    # null-window probe, re-search on a better score
                        s = -self._negamax(depth - 1, -alpha - 1, -alpha, 1)
                        if s > alpha:
                            s = -self._negamax(depth - 1, -INF, -alpha, 1)
                    b.pop()
                    legal += 1
                    if best_here is None or s > alpha:
                        alpha, best_here = s, m
                best = best_here                         # only reached when the iteration finished
                root.remove(best)
                root.insert(0, best)
                if abs(alpha) > MATE_LIMIT:
                    break
                took = time.monotonic() - iteration_start
                remaining = self.level.seconds - (time.monotonic() - self.start)
                if remaining < took * 2.0:
                    break                                # next depth would not finish in time
        except _Stop:
            pass
        return best

    def _noisy_root(self, root):
        b = self.board
        scored = []
        for m in root:
            b.push(m)
            s = -self._negamax(self.level.depth - 1, -INF, INF, 1)
            b.pop()
            scored.append((s + random.gauss(0, self.level.noise), m))
        return max(scored, key=lambda t: t[0])[1]


# ---------------------------------------------------------------- Stockfish (optional)
def find_stockfish():
    candidates = [os.environ.get("STOCKFISH_PATH"), shutil.which("stockfish")]
    here = os.path.dirname(os.path.abspath(sys.argv[0] or "."))
    bundled = getattr(sys, "_MEIPASS", here)
    machine = host_platform.machine().lower()
    android_names = (("stockfish_arm64.bin", "stockfish_armv7.bin")
                     if machine in ("aarch64", "arm64") else
                     ("stockfish_armv7.bin", "stockfish_arm64.bin"))
    candidates += [os.path.join(root, name)
                   for root in (here, bundled, os.path.dirname(__file__))
                   for name in ("stockfish", "stockfish.exe", *android_names)]
    candidates += ["/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish", "/usr/games/stockfish"]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    # Android packages the engine as an app resource. Copy it to writable app
    # storage because executables cannot be launched directly from the APK.
    try:
        from kivy.app import App
        from kivy.resources import resource_find
        app = App.get_running_app()
        resource = next((resource_find(name) for name in android_names
                         if resource_find(name)), None)
        if resource is None:
            resource = next((os.path.join(root, name)
                             for root in (here, os.path.dirname(__file__))
                             for name in android_names
                             if os.path.isfile(os.path.join(root, name))), None)
        if app is not None and resource and os.path.isfile(resource):
            destination = os.path.join(app.user_data_dir, "stockfish")
            shutil.copyfile(resource, destination)
            os.chmod(destination, 0o700)
            return destination
    except Exception:
        pass
    return None


class StockfishEngine:
    """Minimal UCI client."""

    def __init__(self, path, elo):
        flags = 0x08000000 if os.name == "nt" else 0          # no console window on Windows
        self.proc = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                     creationflags=flags)
        self._send("uci")
        self._wait("uciok")
        # UCI_Elo gives a selectable elite-level challenge rather than the
        # engine's maximum strength. Stockfish documents this as an approximate
        # calibration, not a promise that it will play like a particular person.
        self._send("setoption name UCI_LimitStrength value true")
        self._send(f"setoption name UCI_Elo value {elo}")
        self._send("setoption name Threads value 1")
        self._send("setoption name Hash value 64")
        self._send("isready")
        self._wait("readyok")

    def _send(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _wait(self, prefix):
        for line in self.proc.stdout:
            if line.startswith(prefix):
                return line
        raise RuntimeError("engine closed")

    def best_move(self, fen, millis):
        self._send(f"position fen {fen}")
        self._send(f"go movetime {millis}")
        return self._wait("bestmove").split()[1]

    def close(self):
        try:
            self._send("quit")
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.kill()


class ChessAI:
    def __init__(self, level_name="Normal", use_stockfish=True):
        self.level = LEVEL_BY_NAME[level_name]
        self.use_stockfish = use_stockfish
        self._sf = None
        self._sf_failed = False
        self._sf_checked = False
        self._sf_path = None
        self._tt = {}
        self._lock = threading.Lock()

    def set_level(self, name):
        self.level = LEVEL_BY_NAME[name]

    def set_use_stockfish(self, enabled):
        enabled = bool(enabled)
        if enabled != self.use_stockfish:
            self.use_stockfish = enabled
            self._sf_failed = False
            self._sf_checked = False

    def reset(self):
        """Forget transposition-table knowledge from the previous game."""
        # A cancelled worker may still be unwinding; dict.clear is atomic under
        # CPython's GIL and avoids making a new-game action wait on that worker.
        self._tt.clear()

    def _find_stockfish(self):
        """Look for Stockfish once, not on every screen refresh."""
        if not self._sf_checked:
            self._sf_path = find_stockfish() if self.use_stockfish else None
            self._sf_checked = True
        return self._sf_path

    def note(self):
        """Short text telling the player which engine plays the current level."""
        if not self.level.stockfish_elo:
            return ""
        if not self.use_stockfish:
            return "Built-in engine selected."
        if self._sf is not None:
            return f"Engine: Stockfish ({self.level.stockfish_elo} Elo target)."
        if self.use_stockfish and not self._sf_failed and self._find_stockfish():
            return f"Engine: Stockfish will target {self.level.stockfish_elo} Elo."
        return "Stockfish not found, using the built-in engine."

    def _stockfish(self):
        if not self.use_stockfish or self._sf_failed:
            return None
        if self._sf is None:
            path = self._find_stockfish()
            try:
                if path is None:
                    raise FileNotFoundError
                self._sf = StockfishEngine(path, self.level.stockfish_elo)
            except Exception:
                self._sf_failed = True
                return None
        return self._sf

    def choose_move(self, board, cancel):
        """Blocking. Run on a worker thread. `cancel` is a threading.Event."""
        legal = board.legal_moves()
        if not legal:
            return None
        lv = self.level
        if lv.blunder and random.random() < lv.blunder:
            return random.choice(legal)
        if lv.stockfish_elo:
            with self._lock:
                sf = self._stockfish()
                if sf is not None:
                    try:
                        move = board.parse_uci(sf.best_move(board.fen(), int(lv.seconds * 1000)))
                        if move is not None:
                            return move
                    except Exception:
                        self._sf, self._sf_failed = None, True
        # The search builds only acyclic lists, tuples and dicts, so cyclic garbage
        # collection is unnecessary while it runs. Disabling it avoids long gen-2
        # pauses that make the UI stutter on slower machines.
        gc_was_enabled = gc.isenabled()
        if gc_was_enabled:
            gc.disable()
        try:
            return Search(board.copy(), lv, cancel, self._tt).run()
        finally:
            if gc_was_enabled:
                gc.enable()
    def close(self):
        if self._sf is not None:
            self._sf.close()
            self._sf = None
