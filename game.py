"""Game controller: selection, moves, undo and AI turns. No UI code, so any front end can use it."""

import threading

from ai import ChessAI
from board import Board
from pieces import WHITE, COLOR_NAMES


class Game:
    def __init__(self, post=None, on_change=None):
        """post(fn): run fn on the UI thread (Kivy: Clock.schedule_once). Defaults to a direct call."""
        self.post = post or (lambda fn: fn())
        self.on_change = lambda: None            # silent while the first game is set up
        self.ai = ChessAI()
        self.level_name = "Normal"
        self.human = WHITE
        self.token = 0
        self.cancel = threading.Event()
        self.new_game("Normal", WHITE)
        self.on_change = on_change or (lambda: None)

    # ------------------------------------------------------------ lifecycle
    def new_game(self, level_name, human, use_stockfish=None):
        self._stop_ai()
        self.level_name, self.human = level_name, human
        self.ai.set_level(level_name)
        if use_stockfish is not None:
            self.ai.set_use_stockfish(use_stockfish)
        self.ai.reset()
        self.board = Board()
        self.san_log = []
        self.last_move = None
        self._reset_turn()
        self.on_change()
        self._maybe_ai()

    def _stop_ai(self):
        self.cancel.set()
        self.token += 1
        self.thinking = False

    def _reset_turn(self):
        self.selected, self.targets = None, {}
        self.moves = self.board.legal_moves()
        self.result = self.board.outcome(self.moves)

    # ------------------------------------------------------------ human input
    def click(self, sq):
        """Handle a tap on a square. Returns a list of promotion moves when a choice is needed."""
        if self.result or self.thinking or self.board.turn != self.human:
            return None
        if self.selected is not None and sq in self.targets:
            options = self.targets[sq]
            if len(options) > 1:
                return options
            self.play(options[0])
            return None
        piece = self.board.squares[sq]
        if piece is not None and piece.color == self.human and any(m.frm == sq for m in self.moves):
            self.selected, self.targets = sq, {}
            for m in self.moves:
                if m.frm == sq:
                    self.targets.setdefault(m.to, []).append(m)
        else:
            self.selected, self.targets = None, {}
        self.on_change()
        return None

    def deselect(self):
        if self.selected is not None:
            self.selected, self.targets = None, {}
            self.on_change()

    def play(self, move):
        self.thinking = False
        self.san_log.append(self.board.san(move, self.moves))
        self.board.push(move)
        self.last_move = move
        self._reset_turn()
        self.on_change()
        self._maybe_ai()

    def undo(self):
        if not self.san_log:
            return
        self._stop_ai()
        popped = 0
        while self.san_log and (popped == 0 or self.board.turn != self.human):
            self.board.pop()
            self.san_log.pop()
            popped += 1
        self.last_move = self.board.stack[-1][0] if self.board.stack else None
        self._reset_turn()
        self.on_change()
        self._maybe_ai()

    # ------------------------------------------------------------ computer turn
    def _maybe_ai(self):
        if self.result or self.board.turn == self.human:
            return
        self.thinking = True
        self.cancel = threading.Event()
        token, snapshot, cancel = self.token, self.board.copy(), self.cancel
        self.on_change()

        def work():
            try:
                move = self.ai.choose_move(snapshot, cancel)
            except Exception:
                move = None
            self.post(lambda: self._ai_done(token, move))

        threading.Thread(target=work, daemon=True).start()

    def _ai_done(self, token, move):
        if token != self.token:
            return                                           # game was reset or undone meanwhile
        if move is None:
            self.thinking = False
            self.on_change()
            return
        self.play(move)

    def close(self):
        self._stop_ai()
        self.ai.close()

    # ------------------------------------------------------------ text for the UI
    def status(self):
        b = self.board
        if self.result:
            reason, winner = self.result
            if winner is None:
                return f"Draw by {reason}."
            return f"Checkmate. {COLOR_NAMES[winner]} wins."
        side = COLOR_NAMES[b.turn]
        if self.thinking:
            text = f"{side} (computer) is thinking..."
        else:
            text = f"{side} to move" + (", your turn." if b.turn == self.human else ".")
        return ("Check. " + text) if b.in_check() else text

    def move_text(self):
        parts = []
        for i, san in enumerate(self.san_log):
            parts.append(f"{i // 2 + 1}. {san}" if i % 2 == 0 else san)
        return " ".join(parts)

    def engine_note(self):
        return self.ai.note()
