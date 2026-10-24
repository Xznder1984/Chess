"""All colours in one place so the contrast checker and the UI always agree."""

from functools import lru_cache

# Board squares as (light, dark) for each state.
SQUARES = {
    "normal":   ("#E4E7EA", "#7F95A9"),
    "last":     ("#F3E7A1", "#C9B458"),   # last move played
    "selected": ("#F2B25C", "#D18A2B"),   # piece you picked up
    "check":    ("#EE8C86", "#C4483F"),   # king in check (also stated in the status text)
}

PIECE_WHITE = {"fill": "#FFFFFF", "outline": "#000000"}
PIECE_BLACK = {"fill": "#141414", "outline": "#F5F5F5"}
MARKER = "#111111"        # move dots, capture rings and the keyboard cursor border

UI_BG = "#E1E6EA"
UI_TEXT = "#14181C"
BUTTON_BG = "#27374A"
BUTTON_TEXT = "#FFFFFF"
BUTTON_ON_BG = "#0B5E45"  # selected toggle in the new-game dialog (also spelled out in text)


@lru_cache(maxsize=None)
def rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (alpha,)
