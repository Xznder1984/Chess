"""Run with:  python test_engine.py   (no Kivy needed)"""
import time
from board import Board, perft, START_FEN, move_uci
from game import Game
from pieces import WHITE, BLACK

PERFT = [
    (START_FEN, [20, 400, 8902]),
    ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039, 97862]),
    ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812]),
    ("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467]),
    ("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486, 62379]),
]


def test_perft():
    for fen, counts in PERFT:
        b = Board(fen)
        for depth, expected in enumerate(counts, 1):
            got = perft(b, depth)
            assert got == expected, f"perft({depth}) {fen}: {got} != {expected}"
        assert b.fen() == Board(fen).fen()
    print("perft ok")


def test_notation_and_rules():
    b = Board()
    seq = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5c6", "d7c6", "e1g1"]
    sans = []
    for u in seq:
        m = b.parse_uci(u)
        sans.append(b.san(m))
        b.push(m)
    assert sans == ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Bxc6", "dxc6", "O-O"], sans
    assert b.fen().startswith("r1bqkbnr/1pp2ppp/p1p5/4p3/4P3/5N2/PPPP1PPP/RNBQ1RK1 b kq")
    while b.stack:
        b.pop()
    assert b.fen() == START_FEN
    # fool's mate
    b = Board()
    for u in ("f2f3", "e7e5", "g2g4", "d8h4"):
        b.push(b.parse_uci(u))
    assert b.outcome() == ("checkmate", BLACK)
    # stalemate and insufficient material
    assert Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1").outcome() == ("stalemate", None)
    assert Board("8/8/4k3/8/8/3K4/8/8 w - - 0 1").outcome() == ("insufficient material", None)
    print("notation and rules ok")


def test_ai_levels():
    from ai import LEVELS, ChessAI
    import threading
    mate_in_one = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
    ai = ChessAI(use_stockfish=False)
    for lv in LEVELS:
        ai.set_level(lv.name)
        b = Board(mate_in_one if lv.name != "Baby" else START_FEN)
        t = time.time()
        m = ai.choose_move(b, threading.Event())
        dt = time.time() - t
        assert m in b.legal_moves()
        if lv.name in ("Normal", "Hard", "Grandmaster"):
            assert move_uci(m) == "a1a8", (lv.name, move_uci(m))
        print(f"  {lv.name:12s} {move_uci(m)}  {dt:.2f}s")
    print("ai levels ok")


def test_game_flow():
    g = Game()
    g.new_game("Baby", WHITE)
    assert g.click(52) is None and g.selected == 52 and set(g.targets) == {44, 36}
    g.click(36)
    assert g.san_log[0] == "e4"
    for _ in range(50):                      # wait for the random reply on its thread
        if not g.thinking:
            break
        time.sleep(0.1)
    assert len(g.san_log) == 2 and not g.thinking
    g.undo()
    assert g.san_log == [] and g.board.fen() == START_FEN
    print("game flow ok")


if __name__ == "__main__":
    t = time.time()
    test_perft()
    test_notation_and_rules()
    print("AI levels:")
    test_ai_levels()
    test_game_flow()
    print(f"all passed in {time.time() - t:.1f}s")
