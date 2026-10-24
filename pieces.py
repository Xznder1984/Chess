"""Pieces: colours, kinds, glyphs, values and movement tables.

No board state lives here. Squares are numbered 0..63 in FEN order:
0 = a8, 7 = h8, 56 = a1, 63 = h1.
"""

WHITE, BLACK = 0, 1
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = range(6)

KIND_NAMES = ("pawn", "knight", "bishop", "rook", "queen", "king")
COLOR_NAMES = ("White", "Black")
FEN_LETTERS = "pnbrqk"
# Solid glyphs for both sides; the UI separates the sides by fill and outline colour.
GLYPHS = "\u265f\u265e\u265d\u265c\u265b\u265a"
VALUES = (100, 320, 330, 500, 900, 0)  # centipawns; the king is handled by mate scores


class Piece:
    """One immutable piece type. Only 12 instances exist, so `is` comparisons work."""

    __slots__ = ("color", "kind", "index", "fen", "glyph", "value", "name")

    def __init__(self, color, kind):
        self.color = color
        self.kind = kind
        self.index = color * 6 + kind
        letter = FEN_LETTERS[kind]
        self.fen = letter.upper() if color == WHITE else letter
        self.glyph = GLYPHS[kind]
        self.value = VALUES[kind]
        self.name = f"{COLOR_NAMES[color]} {KIND_NAMES[kind]}"

    def __repr__(self):
        return f"<{self.name}>"


BY_INDEX = [Piece(i // 6, i % 6) for i in range(12)]
_FROM_FEN = {p.fen: p for p in BY_INDEX}


def piece(color, kind):
    return BY_INDEX[color * 6 + kind]


def from_fen(letter):
    return _FROM_FEN[letter]


# ---------------------------------------------------------------- movement tables
KNIGHT_STEPS = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))
KING_STEPS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
BISHOP_DIRS = ((-1, -1), (-1, 1), (1, -1), (1, 1))
ROOK_DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1))
QUEEN_DIRS = BISHOP_DIRS + ROOK_DIRS


def _inside(r, c):
    return 0 <= r < 8 and 0 <= c < 8


def _targets(steps):
    return [[(r + dr) * 8 + c + dc for dr, dc in steps if _inside(r + dr, c + dc)]
            for r in range(8) for c in range(8)]


def _rays(dirs):
    table = []
    for r in range(8):
        for c in range(8):
            rays = []
            for dr, dc in dirs:
                ray, rr, cc = [], r + dr, c + dc
                while _inside(rr, cc):
                    ray.append(rr * 8 + cc)
                    rr += dr
                    cc += dc
                if ray:
                    rays.append(ray)
            table.append(rays)
    return table


KNIGHT_TARGETS = _targets(KNIGHT_STEPS)
KING_TARGETS = _targets(KING_STEPS)
BISHOP_RAYS = _rays(BISHOP_DIRS)
ROOK_RAYS = _rays(ROOK_DIRS)
QUEEN_RAYS = _rays(QUEEN_DIRS)
# Squares a pawn of the given colour attacks from each square.
PAWN_CAPTURES = (_targets(((-1, -1), (-1, 1))), _targets(((1, -1), (1, 1))))

# ---------------------------------------------------------------- evaluation tables
# Kept here (not in ai.py) so Board can update a running evaluation as pieces move
# without importing the search module. Used only by the AI.
PHASE = (0, 1, 1, 2, 4, 0)


def _build_positional_tables():
    """Piece-square tables from White's point of view, indexed like board squares."""
    def central(r, c):
        return min(r, 7 - r) + min(c, 7 - c)          # 0 (corner) .. 6 (centre)

    pawn_adv = (0, 0, 5, 10, 20, 35, 60, 0)
    pawn_file = (-5, 0, 3, 8, 8, 3, 0, -5)
    king_back = (10, 20, 5, 0, 0, 5, 20, 15)
    t = {k: [0] * 64 for k in (PAWN, KNIGHT, BISHOP, ROOK, QUEEN)}
    king_mg, king_eg = [0] * 64, [0] * 64
    for r in range(8):
        for c in range(8):
            s, rank = r * 8 + c, 7 - r                   # rank 0 = White's back rank
            t[PAWN][s] = pawn_adv[rank] + (pawn_file[c] if 1 <= rank <= 4 else 0)
            t[KNIGHT][s] = (central(r, c) - 3) * 14
            t[BISHOP][s] = (central(r, c) - 3) * 6
            t[ROOK][s] = (10 if rank == 6 else 0) + (3 if c in (3, 4) else 0)
            t[QUEEN][s] = (central(r, c) - 3) * 3
            king_mg[s] = king_back[c] if rank == 0 else (-15 * rank - 10 + (5 if c in (0, 1, 6, 7) else 0))
            king_eg[s] = (central(r, c) - 3) * 12
    return t, king_mg, king_eg


PST, KING_MG, KING_EG = _build_positional_tables()

# Per piece index (colour * 6 + kind) and square: signed White-point-of-view score,
# signed material, and game phase. Black squares are mirrored inside the table.
EVAL_SCORE = [[0] * 64 for _ in range(12)]
EVAL_MATERIAL = [0] * 12
EVAL_PHASE = [0] * 12
for _kind in range(6):
    for _color in (WHITE, BLACK):
        _i = _color * 6 + _kind
        EVAL_MATERIAL[_i] = VALUES[_kind] if _color == WHITE else -VALUES[_kind]
        EVAL_PHASE[_i] = PHASE[_kind]
        if _kind == KING:
            continue
        _row = EVAL_SCORE[_i]
        _pst = PST[_kind]
        for _s in range(64):
            _v = VALUES[_kind] + _pst[_s if _color == WHITE else _s ^ 56]
            _row[_s] = _v if _color == WHITE else -_v
del _kind, _color, _i, _row, _pst, _s, _v

