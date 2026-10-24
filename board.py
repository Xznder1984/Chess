"""Board: position state, legal move generation, make/unmake, FEN, SAN and game outcome."""

import random
from typing import NamedTuple

from pieces import (
    WHITE, BLACK, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING, FEN_LETTERS,
    piece, from_fen,
    KNIGHT_TARGETS, KING_TARGETS, BISHOP_RAYS, ROOK_RAYS, QUEEN_RAYS, PAWN_CAPTURES,
    EVAL_SCORE, EVAL_MATERIAL, EVAL_PHASE,
)

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FILES = "abcdefgh"
WK, WQ, BK, BQ = 1, 2, 4, 8  # castling-right bits
_BISHOP_W, _BISHOP_B = BISHOP, BISHOP + 6


class Move(NamedTuple):
    frm: int
    to: int
    promo: int = 0  # 0 = no promotion (a pawn can never be a promotion target)


def square_name(sq):
    return FILES[sq & 7] + str(8 - (sq >> 3))


def name_to_square(name):
    return (8 - int(name[1])) * 8 + FILES.index(name[0])


def move_uci(m):
    return square_name(m.frm) + square_name(m.to) + (FEN_LETTERS[m.promo] if m.promo else "")


# ---------------------------------------------------------------- hashing / tables
_rng = random.Random(20260601)
_ZPIECE = [[_rng.getrandbits(64) for _ in range(64)] for _ in range(12)]
_ZSIDE = _rng.getrandbits(64)
_ZCASTLE = [_rng.getrandbits(64) for _ in range(16)]
_ZEP = [_rng.getrandbits(64) for _ in range(8)]

_CASTLE_MASK = [15] * 64
for _sq, _clear in ((60, WK | WQ), (63, WK), (56, WQ), (4, BK | BQ), (7, BK), (0, BQ)):
    _CASTLE_MASK[_sq] = 15 & ~_clear


class Board:
    def __init__(self, fen=START_FEN):
        self.set_fen(fen)

    # ------------------------------------------------------------ setup / export
    def set_fen(self, fen):
        parts = fen.split()
        self.squares = [None] * 64
        sq = 0
        for ch in parts[0]:
            if ch == "/":
                continue
            if ch.isdigit():
                sq += int(ch)
            else:
                self.squares[sq] = from_fen(ch)
                sq += 1
        self.turn = WHITE if parts[1] == "w" else BLACK
        self.castling = 0
        for ch in parts[2]:
            self.castling |= {"K": WK, "Q": WQ, "k": BK, "q": BQ}.get(ch, 0)
        self.ep = None
        self.halfmove = int(parts[4]) if len(parts) > 4 else 0
        self.fullmove = int(parts[5]) if len(parts) > 5 else 1
        self.king_sq = [self.squares.index(piece(WHITE, KING)),
                        self.squares.index(piece(BLACK, KING))]
        self._compute_eval()
        if len(parts) > 3 and parts[3] != "-":
            ep = name_to_square(parts[3])
            if self._ep_capturable(ep):
                self.ep = ep
        self.stack = []
        self.key = self._compute_key()
        self.key_history = [self.key]

    def fen(self):
        rows = []
        for r in range(8):
            row, empty = "", 0
            for c in range(8):
                p = self.squares[r * 8 + c]
                if p is None:
                    empty += 1
                else:
                    row += (str(empty) if empty else "") + p.fen
                    empty = 0
            rows.append(row + (str(empty) if empty else ""))
        rights = "".join(ch for bit, ch in ((WK, "K"), (WQ, "Q"), (BK, "k"), (BQ, "q"))
                         if self.castling & bit) or "-"
        ep = square_name(self.ep) if self.ep is not None else "-"
        return (f"{'/'.join(rows)} {'w' if self.turn == WHITE else 'b'} {rights} {ep} "
                f"{self.halfmove} {self.fullmove}")

    def _compute_eval(self):
        """Recompute the running evaluation state (used after set_fen)."""
        score, material, phase = 0, 0, 0
        wb = bb = 0
        st, mt, pt = EVAL_SCORE, EVAL_MATERIAL, EVAL_PHASE
        for s, p in enumerate(self.squares):
            if p is None:
                continue
            i = p.index
            score += st[i][s]
            material += mt[i]
            phase += pt[i]
            if i == _BISHOP_W:
                wb += 1
            elif i == _BISHOP_B:
                bb += 1
        self.eval_score = score
        self.eval_material = material
        self.eval_phase = phase
        self.bishop_w = wb
        self.bishop_b = bb

    def copy(self):
        """Independent copy for the AI thread (undo history is not copied)."""
        b = Board.__new__(Board)
        b.squares = self.squares[:]
        b.turn, b.castling, b.ep = self.turn, self.castling, self.ep
        b.halfmove, b.fullmove = self.halfmove, self.fullmove
        b.king_sq = self.king_sq[:]
        b.stack = []
        b.key = self.key
        b.key_history = self.key_history[:]
        b.eval_score, b.eval_material, b.eval_phase = self.eval_score, self.eval_material, self.eval_phase
        b.bishop_w, b.bishop_b = self.bishop_w, self.bishop_b
        return b

    def _compute_key(self):
        key = 0
        for s, p in enumerate(self.squares):
            if p is not None:
                key ^= _ZPIECE[p.index][s]
        if self.turn == BLACK:
            key ^= _ZSIDE
        key ^= _ZCASTLE[self.castling]
        if self.ep is not None:
            key ^= _ZEP[self.ep & 7]
        return key

    def _ep_capturable(self, ep):
        """True if the side to move has a pawn that could capture on `ep` (used for hashing)."""
        mover = self.turn
        pawn = piece(mover, PAWN)
        return any(self.squares[s] is pawn for s in PAWN_CAPTURES[1 - mover][ep])

    # ------------------------------------------------------------ attacks
    def attacked(self, target, by):
        """True if any piece of colour `by` attacks square `target`."""
        sq = self.squares
        for s in PAWN_CAPTURES[1 - by][target]:
            p = sq[s]
            if p is not None and p.color == by and p.kind == PAWN:
                return True
        for s in KNIGHT_TARGETS[target]:
            p = sq[s]
            if p is not None and p.color == by and p.kind == KNIGHT:
                return True
        for s in KING_TARGETS[target]:
            p = sq[s]
            if p is not None and p.color == by and p.kind == KING:
                return True
        for ray in BISHOP_RAYS[target]:
            for s in ray:
                p = sq[s]
                if p is not None:
                    if p.color == by and (p.kind == BISHOP or p.kind == QUEEN):
                        return True
                    break
        for ray in ROOK_RAYS[target]:
            for s in ray:
                p = sq[s]
                if p is not None:
                    if p.color == by and (p.kind == ROOK or p.kind == QUEEN):
                        return True
                    break
        return False

    def in_check(self):
        return self.attacked(self.king_sq[self.turn], 1 - self.turn)

    # ------------------------------------------------------------ move generation
    def pseudo_moves(self, captures_only=False):
        """Moves that obey piece movement but may leave the own king in check.
        Castling is fully checked here. With captures_only: captures and queen promotions."""
        sq, color = self.squares, self.turn
        moves = []
        add = moves.append
        knight_t, king_t = KNIGHT_TARGETS, KING_TARGETS
        bishop_r, rook_r, queen_r = BISHOP_RAYS, ROOK_RAYS, QUEEN_RAYS
        pawn_cap = PAWN_CAPTURES[color]
        ep = self.ep
        if color == WHITE:
            step, start_row, last_row = -8, 6, 0
        else:
            step, start_row, last_row = 8, 1, 7
        for frm, p in enumerate(sq):
            if p is None or p.color != color:
                continue
            kind = p.kind
            if kind == PAWN:
                one = frm + step
                promo_next = (one >> 3) == last_row
                if sq[one] is None:
                    if promo_next:
                        if captures_only:
                            add(Move(frm, one, QUEEN))
                        else:
                            add(Move(frm, one, QUEEN))
                            add(Move(frm, one, ROOK))
                            add(Move(frm, one, BISHOP))
                            add(Move(frm, one, KNIGHT))
                    elif not captures_only:
                        add(Move(frm, one))
                        if (frm >> 3) == start_row and sq[one + step] is None:
                            add(Move(frm, one + step))
                for to in pawn_cap[frm]:
                    t = sq[to]
                    if (t is not None and t.color != color) or (t is None and to == ep):
                        if promo_next:
                            add(Move(frm, to, QUEEN))
                            add(Move(frm, to, ROOK))
                            add(Move(frm, to, BISHOP))
                            add(Move(frm, to, KNIGHT))
                        else:
                            add(Move(frm, to))
            elif kind == KNIGHT or kind == KING:
                for to in (knight_t if kind == KNIGHT else king_t)[frm]:
                    t = sq[to]
                    if t is None:
                        if not captures_only:
                            add(Move(frm, to))
                    elif t.color != color:
                        add(Move(frm, to))
            else:
                rays = bishop_r if kind == BISHOP else rook_r if kind == ROOK else queen_r
                for ray in rays[frm]:
                    for to in ray:
                        t = sq[to]
                        if t is None:
                            if not captures_only:
                                add(Move(frm, to))
                        else:
                            if t.color != color:
                                add(Move(frm, to))
                            break
        if self.castling and not captures_only:
            self._castle_moves(color, moves)
        return moves

    def _castle_moves(self, color, moves):
        sq, enemy, att = self.squares, 1 - color, self.attacked
        if color == WHITE:
            if (self.castling & WK and sq[61] is None and sq[62] is None
                    and not (att(60, enemy) or att(61, enemy) or att(62, enemy))):
                moves.append(Move(60, 62))
            if (self.castling & WQ and sq[59] is None and sq[58] is None and sq[57] is None
                    and not (att(60, enemy) or att(59, enemy) or att(58, enemy))):
                moves.append(Move(60, 58))
        else:
            if (self.castling & BK and sq[5] is None and sq[6] is None
                    and not (att(4, enemy) or att(5, enemy) or att(6, enemy))):
                moves.append(Move(4, 6))
            if (self.castling & BQ and sq[3] is None and sq[2] is None and sq[1] is None
                    and not (att(4, enemy) or att(3, enemy) or att(2, enemy))):
                moves.append(Move(4, 2))

    def legal_moves(self):
        out, me = [], self.turn
        for m in self.pseudo_moves():
            self.push(m)
            if not self.attacked(self.king_sq[me], self.turn):
                out.append(m)
            self.pop()
        return out

    # ------------------------------------------------------------ make / unmake
    def push(self, m):
        sq, color = self.squares, self.turn
        frm, to, promo = m
        p = sq[frm]
        captured, cap_sq = sq[to], to
        key = self.key ^ _ZSIDE ^ _ZCASTLE[self.castling]
        if self.ep is not None:
            key ^= _ZEP[self.ep & 7]
        kind = p.kind

        if kind == PAWN and to == self.ep and captured is None:   # en passant
            cap_sq = (frm & ~7) | (to & 7)
            captured = sq[cap_sq]
            sq[cap_sq] = None
        if captured is not None:
            key ^= _ZPIECE[captured.index][cap_sq]

        # Keep the running evaluation in step with the position. Quiet moves only
        # change the piece-square term; material and phase change on captures/promotions.
        st = EVAL_SCORE
        pi = p.index
        if captured is None and promo == 0:
            self.eval_score += st[pi][to] - st[pi][frm]
        else:
            e_score = self.eval_score - st[pi][frm]
            e_mat = self.eval_material - EVAL_MATERIAL[pi]
            e_phase = self.eval_phase - EVAL_PHASE[pi]
            wb, bb = self.bishop_w, self.bishop_b
            if pi == _BISHOP_W:
                wb -= 1
            elif pi == _BISHOP_B:
                bb -= 1
            if captured is not None:
                ci = captured.index
                e_score -= st[ci][cap_sq]
                e_mat -= EVAL_MATERIAL[ci]
                e_phase -= EVAL_PHASE[ci]
                if ci == _BISHOP_W:
                    wb -= 1
                elif ci == _BISHOP_B:
                    bb -= 1
            placed = piece(color, promo) if promo else p
            qi = placed.index
            e_score += st[qi][to]
            e_mat += EVAL_MATERIAL[qi]
            e_phase += EVAL_PHASE[qi]
            if qi == _BISHOP_W:
                wb += 1
            elif qi == _BISHOP_B:
                bb += 1
            self.eval_score, self.eval_material, self.eval_phase = e_score, e_mat, e_phase
            self.bishop_w, self.bishop_b = wb, bb

        self.stack.append((m, captured, cap_sq, self.castling, self.ep, self.halfmove, self.key))
        if promo:
            placed = piece(color, promo)
        else:
            placed = p
        qi = placed.index
        sq[frm] = None
        sq[to] = placed
        key ^= _ZPIECE[p.index][frm] ^ _ZPIECE[qi][to]

        if kind == KING:
            self.king_sq[color] = to
            if to - frm == 2 or frm - to == 2:                      # castling: move the rook
                rf, rt = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
                rook = sq[rf]
                sq[rf], sq[rt] = None, rook
                ri = rook.index
                key ^= _ZPIECE[ri][rf] ^ _ZPIECE[ri][rt]
                self.eval_score += st[ri][rt] - st[ri][rf]

        self.castling &= _CASTLE_MASK[frm] & _CASTLE_MASK[to]
        key ^= _ZCASTLE[self.castling]

        self.ep = None
        if kind == PAWN and (to - frm == 16 or frm - to == 16):
            mid = (frm + to) // 2
            enemy = piece(1 - color, PAWN)
            f = to & 7
            if (f > 0 and sq[to - 1] is enemy) or (f < 7 and sq[to + 1] is enemy):
                self.ep = mid
                key ^= _ZEP[mid & 7]

        self.halfmove = 0 if (kind == PAWN or captured is not None) else self.halfmove + 1
        if color == BLACK:
            self.fullmove += 1
        self.turn = 1 - color
        self.key = key
        self.key_history.append(key)

    def pop(self):
        m, captured, cap_sq, castling, ep, halfmove, key = self.stack.pop()
        self.key_history.pop()
        self.turn = color = 1 - self.turn
        sq = self.squares
        if m is None:                                               # null move
            self.castling, self.ep, self.halfmove, self.key = castling, ep, halfmove, key
            return
        frm, to, promo = m
        p = sq[to]
        placed = p
        if promo:
            p = piece(color, PAWN)

        # Reverse the incremental evaluation update made by push().
        st = EVAL_SCORE
        qi = placed.index
        if captured is None and promo == 0:
            self.eval_score += st[qi][frm] - st[qi][to]
        else:
            e_score = self.eval_score - st[qi][to]
            e_mat = self.eval_material - EVAL_MATERIAL[qi]
            e_phase = self.eval_phase - EVAL_PHASE[qi]
            wb, bb = self.bishop_w, self.bishop_b
            if qi == _BISHOP_W:
                wb -= 1
            elif qi == _BISHOP_B:
                bb -= 1
            pi = p.index
            e_score += st[pi][frm]
            e_mat += EVAL_MATERIAL[pi]
            e_phase += EVAL_PHASE[pi]
            if pi == _BISHOP_W:
                wb += 1
            elif pi == _BISHOP_B:
                bb += 1
            if captured is not None:
                ci = captured.index
                e_score += st[ci][cap_sq]
                e_mat += EVAL_MATERIAL[ci]
                e_phase += EVAL_PHASE[ci]
                if ci == _BISHOP_W:
                    wb += 1
                elif ci == _BISHOP_B:
                    bb += 1
            self.eval_score, self.eval_material, self.eval_phase = e_score, e_mat, e_phase
            self.bishop_w, self.bishop_b = wb, bb
        if p.kind == KING and (to - frm == 2 or frm - to == 2):
            rf, rt = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
            ri = sq[rt].index
            self.eval_score += st[ri][rf] - st[ri][rt]

        sq[frm] = p
        sq[to] = None
        if captured is not None:
            sq[cap_sq] = captured
        if p.kind == KING:
            self.king_sq[color] = frm
            if to - frm == 2 or frm - to == 2:
                rf, rt = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
                sq[rf], sq[rt] = sq[rt], None
        if color == BLACK:
            self.fullmove -= 1
        self.castling, self.ep, self.halfmove, self.key = castling, ep, halfmove, key

    def push_null(self):
        """Pass the turn (used by the AI's null-move pruning)."""
        self.stack.append((None, None, None, self.castling, self.ep, self.halfmove, self.key))
        if self.ep is not None:
            self.key ^= _ZEP[self.ep & 7]
            self.ep = None
        self.key ^= _ZSIDE
        self.turn = 1 - self.turn
        self.halfmove += 1
        self.key_history.append(self.key)

    pop_null = pop

    # ------------------------------------------------------------ game state
    def is_repetition(self):
        """True if the current position occurred earlier (within the reversible window)."""
        h = self.key_history
        start = len(h) - self.halfmove - 1
        if start < 0:
            start = 0
        return self.key in h[start:len(h) - 1]

    def repetition_count(self):
        return self.key_history[-self.halfmove - 1:].count(self.key)

    def insufficient_material(self):
        minors = []
        for s, p in enumerate(self.squares):
            if p is None or p.kind == KING:
                continue
            if p.kind in (PAWN, ROOK, QUEEN):
                return False
            minors.append((p.kind, ((s >> 3) + (s & 7)) & 1))
        if len(minors) <= 1:
            return True
        return all(k == BISHOP for k, _ in minors) and len({c for _, c in minors}) == 1

    def outcome(self, legal=None):
        """None while play continues, else (reason, winner); winner is WHITE, BLACK or None."""
        legal = self.legal_moves() if legal is None else legal
        if not legal:
            return ("checkmate", 1 - self.turn) if self.in_check() else ("stalemate", None)
        if self.insufficient_material():
            return ("insufficient material", None)
        if self.halfmove >= 100:
            return ("fifty-move rule", None)
        if self.repetition_count() >= 3:
            return ("threefold repetition", None)
        return None

    # ------------------------------------------------------------ notation
    def san(self, m, legal=None):
        """Standard algebraic notation of a legal move. Call before push().
        Pass `legal` (the current legal move list) when it is already known."""
        sq = self.squares
        p = sq[m.frm]
        if p.kind == KING and abs(m.to - m.frm) == 2:
            s = "O-O" if m.to > m.frm else "O-O-O"
        else:
            capture = sq[m.to] is not None or (p.kind == PAWN and (m.frm & 7) != (m.to & 7))
            if p.kind == PAWN:
                s = (FILES[m.frm & 7] + "x" if capture else "") + square_name(m.to)
                if m.promo:
                    s += "=" + FEN_LETTERS[m.promo].upper()
            else:
                s = FEN_LETTERS[p.kind].upper()
                others = [o for o in (self.legal_moves() if legal is None else legal)
                          if o.to == m.to and o.frm != m.frm and sq[o.frm] is p]
                if others:
                    if not any((o.frm & 7) == (m.frm & 7) for o in others):
                        s += FILES[m.frm & 7]
                    elif not any((o.frm >> 3) == (m.frm >> 3) for o in others):
                        s += str(8 - (m.frm >> 3))
                    else:
                        s += square_name(m.frm)
                s += ("x" if capture else "") + square_name(m.to)
        self.push(m)
        if self.in_check():
            s += "+" if self.legal_moves() else "#"
        self.pop()
        return s

    def parse_uci(self, text):
        for m in self.legal_moves():
            if move_uci(m) == text:
                return m
        return None


def perft(board, depth):
    """Count leaf positions; used by the tests to prove move generation is correct."""
    if depth == 0:
        return 1
    total, me = 0, board.turn
    for m in board.pseudo_moves():
        board.push(m)
        if not board.attacked(board.king_sq[me], board.turn):
            total += 1 if depth == 1 else perft(board, depth - 1)
        board.pop()
    return total
