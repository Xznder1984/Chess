"""WCAG 2.x contrast check for every colour pair the UI uses.  Run: python contrast_check.py
Text needs 4.5:1. Shapes that carry meaning (piece outlines, dots, rings) need 3:1."""
import sys
import theme as T


def luminance(hex_color):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    h = hex_color.lstrip("#")
    r, g, b = (lin(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def pairs():
    for state, squares in T.SQUARES.items():
        for tone, bg in zip(("light", "dark"), squares):
            tag = f"{state} {tone} square"
            yield f"White piece outline on {tag}", T.PIECE_WHITE["outline"], bg, 3.0
            yield f"Black piece body on {tag}", T.PIECE_BLACK["fill"], bg, 3.0
            yield f"Move dot / capture ring on {tag}", T.MARKER, bg, 3.0
    yield "White piece body vs its outline", T.PIECE_WHITE["fill"], T.PIECE_WHITE["outline"], 3.0
    yield "Black piece body vs its outline", T.PIECE_BLACK["fill"], T.PIECE_BLACK["outline"], 3.0
    yield "White body vs black body (sides distinct)", T.PIECE_WHITE["fill"], T.PIECE_BLACK["fill"], 3.0
    yield "Status, move list and coordinates text", T.UI_TEXT, T.UI_BG, 4.5
    yield "Button text", T.BUTTON_TEXT, T.BUTTON_BG, 4.5
    yield "Selected toggle text", T.BUTTON_TEXT, T.BUTTON_ON_BG, 4.5


if __name__ == "__main__":
    failed = 0
    for name, fg, bg, need in pairs():
        r = ratio(fg, bg)
        ok = r >= need
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {r:5.2f}:1 (need {need})  {name}")
    print("\nInfo: white piece body on a light square is only "
          f"{ratio(T.PIECE_WHITE['fill'], T.SQUARES['normal'][0]):.2f}:1, "
          "so white pieces rely on their black outline (checked above).")
    sys.exit(1 if failed else 0)
