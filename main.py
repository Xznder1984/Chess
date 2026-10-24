"""Chess front end (Kivy). Run:  python main.py
Kivy is the one UI toolkit that packages the same code for Windows, macOS, Linux and Android."""

import sys

from kivy.config import Config

# The AI searches on a worker thread. Shorter GIL slices keep the board drawing
# smoothly while that thread is busy, at a negligible cost to search speed.
sys.setswitchinterval(0.001)

Config.set("graphics", "width", "480")
Config.set("graphics", "height", "820")
Config.set("kivy", "exit_on_escape", "0")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line
from kivy.metrics import dp, sp
from kivy.resources import resource_find
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.utils import platform

import theme as T
from ai import LEVELS, LEVEL_BY_NAME
from game import Game
from pieces import WHITE, BLACK, KIND_NAMES

# DejaVu Sans ships inside Kivy (free licence) and contains the chess glyphs.
CHESS_FONT = resource_find("data/fonts/DejaVuSans.ttf")
FILES = "abcdefgh"
ARROWS = {273: (-1, 0), 274: (1, 0), 275: (0, 1), 276: (0, -1)}   # up, down, right, left


class Cell(Button):
    """One board square. A real button, so touch and mouse both work."""

    def __init__(self, **kw):
        super().__init__(background_normal="", background_down="", font_name=CHESS_FONT, **kw)
        self.marker = None
        self.cursor = False
        self.bind(pos=self._overlay, size=self._overlay)
        self.bind(height=lambda w, h: setattr(w, "font_size", h * 0.74))

    def set_overlay(self, marker, cursor):
        if (marker, cursor) != (self.marker, self.cursor):
            self.marker, self.cursor = marker, cursor
            self._overlay()

    def _overlay(self, *_):
        self.canvas.after.clear()
        if not (self.marker or self.cursor):
            return
        with self.canvas.after:
            Color(*T.rgba(T.MARKER))
            cx, cy = self.center
            s = min(self.size)
            if self.marker == "dot":
                r = s * 0.13
                Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
            elif self.marker == "ring":
                Line(circle=(cx, cy, s * 0.43), width=dp(2.2))
            if self.cursor:
                Line(rectangle=(self.x + dp(2), self.y + dp(2), self.width - dp(4), self.height - dp(4)),
                     width=dp(2.5))


class Choice(ToggleButton):
    """Toggle used in the new-game dialog."""

    def __init__(self, **kw):
        super().__init__(background_normal="", background_down="", allow_no_selection=False,
                         color=T.rgba(T.BUTTON_TEXT), **kw)
        self.bind(state=self._paint)
        self._paint()

    def _paint(self, *_):
        self.background_color = T.rgba(T.BUTTON_ON_BG if self.state == "down" else T.BUTTON_BG)


def action_button(text, **kw):
    return Button(text=text, background_normal="", background_down="",
                  background_color=T.rgba(T.BUTTON_BG), color=T.rgba(T.BUTTON_TEXT), **kw)


class SquareHolder(FloatLayout):
    """Keeps its single child square and centred."""

    def __init__(self, child, **kw):
        super().__init__(**kw)
        self.child = child
        child.size_hint = (None, None)
        self.add_widget(child)
        self.bind(pos=self._fit, size=self._fit)

    def _fit(self, *_):
        s = min(self.width, self.height)
        self.child.size = (s, s)
        self.child.pos = (self.x + (self.width - s) / 2, self.y + (self.height - s) / 2)


def ui_label(text="", **kw):
    return Label(text=text, color=T.rgba(T.UI_TEXT), **kw)


class ChessApp(App):
    title = "Chess"

    def build(self):
        Window.clearcolor = T.rgba(T.UI_BG)
        self.flipped = False
        self.cursor = None
        self.popup = None
        self._cell_state = [[None] * 8 for _ in range(8)]

        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        self.status = ui_label(size_hint_y=None, height=dp(56), font_size=sp(17),
                               halign="center", valign="middle")
        self.status.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(self.status)

        # Board with rank numbers on the left and file letters underneath.
        self.cells = [[None] * 8 for _ in range(8)]
        grid = GridLayout(cols=8)
        for r in range(8):
            for c in range(8):
                cell = Cell()
                cell.bind(on_release=lambda _w, r=r, c=c: self.on_cell(r, c))
                self.cells[r][c] = cell
                grid.add_widget(cell)
        self.rank_labels = [ui_label(font_size=sp(13)) for _ in range(8)]
        self.file_labels = [ui_label(font_size=sp(13)) for _ in range(8)]
        ranks = BoxLayout(orientation="vertical", size_hint_x=None, width=dp(22))
        for lab in self.rank_labels:
            ranks.add_widget(lab)
        files = BoxLayout()
        for lab in self.file_labels:
            files.add_widget(lab)
        top = BoxLayout()
        top.add_widget(ranks)
        top.add_widget(grid)
        bottom = BoxLayout(size_hint_y=None, height=dp(22))
        bottom.add_widget(Widget(size_hint_x=None, width=dp(22)))
        bottom.add_widget(files)
        frame = BoxLayout(orientation="vertical")
        frame.add_widget(top)
        frame.add_widget(bottom)
        root.add_widget(SquareHolder(frame))

        # Move list in plain text.
        self.scroll = ScrollView(size_hint_y=None, height=dp(64), do_scroll_x=False)
        self.moves_label = ui_label(size_hint_y=None, halign="left", valign="top", font_size=sp(15))
        self.moves_label.bind(width=lambda w, v: setattr(w, "text_size", (v, None)),
                              texture_size=lambda w, v: setattr(w, "height", max(v[1], dp(24))))
        self.scroll.add_widget(self.moves_label)
        root.add_widget(self.scroll)

        bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        for text, fn in (("New game", lambda *_: self.open_new_game()),
                         ("Undo", lambda *_: self.game.undo()),
                         ("Flip board", lambda *_: self.flip())):
            b = action_button(text, font_size=sp(16))
            b.bind(on_release=fn)
            bar.add_widget(b)
        root.add_widget(bar)

        self.game = Game(post=lambda fn: Clock.schedule_once(lambda _dt: fn(), 0),
                         on_change=self.refresh)
        Window.bind(on_key_down=self.on_key_down)
        self.refresh()
        Clock.schedule_once(lambda _dt: self.open_new_game(first=True), 0)
        return root

    def on_stop(self):
        self.game.close()

    # ------------------------------------------------------------ board <-> screen
    def disp_to_sq(self, row, col):
        return (7 - row) * 8 + (7 - col) if self.flipped else row * 8 + col

    def flip(self):
        self.flipped = not self.flipped
        self.refresh()

    def refresh(self, *_):
        g, b = self.game, self.game.board
        note = g.engine_note()
        status_text = g.status() + (("\n" + note) if note else "")
        if self.status.text != status_text:
            self.status.text = status_text
        moves_text = g.move_text() or "No moves yet."
        if self.moves_label.text != moves_text:
            self.moves_label.text = moves_text
            Clock.schedule_once(lambda _dt: setattr(self.scroll, "scroll_y", 0), 0)
        for c in range(8):
            text = FILES[7 - c] if self.flipped else FILES[c]
            if self.file_labels[c].text != text:
                self.file_labels[c].text = text
        for r in range(8):
            text = str(r + 1) if self.flipped else str(8 - r)
            if self.rank_labels[r].text != text:
                self.rank_labels[r].text = text

        check_sq = b.king_sq[b.turn] if b.in_check() else None
        last = (g.last_move.frm, g.last_move.to) if g.last_move else ()
        for r in range(8):
            for c in range(8):
                sq = self.disp_to_sq(r, c)
                cell = self.cells[r][c]
                p = b.squares[sq]
                if sq == g.selected:
                    state = "selected"
                elif sq == check_sq:
                    state = "check"
                elif sq in last:
                    state = "last"
                else:
                    state = "normal"
                light = ((sq >> 3) + (sq & 7)) % 2 == 0
                bg = T.SQUARES[state][0 if light else 1]
                if p is None:
                    glyph, fill, outline = "", None, None
                else:
                    style = T.PIECE_WHITE if p.color == WHITE else T.PIECE_BLACK
                    glyph, fill, outline = p.glyph, style["fill"], style["outline"]
                marker = None
                if sq in g.targets:
                    marker = "ring" if p is not None else "dot"
                cursor = self.cursor == (r, c)
                state_key = (glyph, fill, outline, bg, marker, cursor)
                if self._cell_state[r][c] == state_key:
                    continue
                self._cell_state[r][c] = state_key
                cell.background_color = T.rgba(bg)
                if cell.text != glyph:
                    cell.text = glyph
                if fill is not None:
                    cell.color = T.rgba(fill)
                    cell.outline_color = T.rgba(outline)
                    cell.outline_width = dp(1.6)
                cell.set_overlay(marker, cursor)

    # ------------------------------------------------------------ input
    def on_cell(self, row, col):
        options = self.game.click(self.disp_to_sq(row, col))
        if options:
            self.ask_promotion(options)

    def on_key_down(self, _window, key, _scancode, codepoint, _modifiers):
        """Keyboard play: arrows move, Enter or Space selects, Esc cancels, U undo, N new, F flip."""
        if self.popup is not None:
            return False
        if key in ARROWS:
            r, c = self.cursor or (6, 4)
            if self.cursor:
                r = min(7, max(0, r + ARROWS[key][0]))
                c = min(7, max(0, c + ARROWS[key][1]))
            self.cursor = (r, c)
            self.refresh()
            return True
        if key in (13, 271, 32) and self.cursor:
            self.on_cell(*self.cursor)
            return True
        if key == 27:
            if self.game.selected is not None or self.cursor:
                self.cursor = None
                self.game.deselect()
                self.refresh()
            elif platform == "android":
                self.stop()
            return True
        letter = (codepoint or "").lower()
        if letter == "u":
            self.game.undo()
        elif letter == "n":
            self.open_new_game()
        elif letter == "f":
            self.flip()
        else:
            return False
        return True

    # ------------------------------------------------------------ dialogs
    def _open(self, popup):
        self.popup = popup
        popup.bind(on_dismiss=lambda *_: setattr(self, "popup", None))
        popup.open()

    def ask_promotion(self, options):
        box = BoxLayout(spacing=dp(8), padding=dp(8))
        pop = Popup(title="Promote pawn to", content=box, size_hint=(0.92, None), height=dp(170))
        for m in options:
            btn = action_button(KIND_NAMES[m.promo].capitalize(), font_size=sp(16))
            btn.bind(on_release=lambda _b, m=m: (pop.dismiss(), self.game.play(m)))
            box.add_widget(btn)
        self._open(pop)

    def open_new_game(self, first=False):
        if self.popup is not None:
            return
        sel = {"level": self.game.level_name, "side": self.game.human}
        body = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10),
                         size_hint_y=None)
        body.bind(minimum_height=body.setter("height"))

        body.add_widget(Label(text="Difficulty", size_hint_y=None, height=dp(24)))
        levels = GridLayout(cols=2, spacing=dp(6), size_hint_y=None, height=dp(3 * 46 + 12))
        desc = Label(size_hint_y=None, height=dp(120), halign="left", valign="top")
        desc.bind(size=lambda w, s: setattr(w, "text_size", s))

        def pick_level(btn):
            sel["level"] = btn.text
            desc.text = f"Selected: {btn.text}. {LEVEL_BY_NAME[btn.text].description}"

        for lv in LEVELS:
            ch = Choice(text=lv.name, group="level", font_size=sp(16),
                        state="down" if lv.name == sel["level"] else "normal")
            ch.bind(on_release=pick_level)
            levels.add_widget(ch)
        desc.text = f"Selected: {sel['level']}. {LEVEL_BY_NAME[sel['level']].description}"
        body.add_widget(levels)
        body.add_widget(desc)

        body.add_widget(Label(text="You play", size_hint_y=None, height=dp(24)))
        sides = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(46))
        for name, side in (("White", WHITE), ("Black", BLACK)):
            ch = Choice(text=name, group="side", font_size=sp(16),
                        state="down" if side == sel["side"] else "normal")
            ch.bind(on_release=lambda _b, side=side: sel.__setitem__("side", side))
            sides.add_widget(ch)
        body.add_widget(sides)

        body.add_widget(Label(text="Grandmaster engine", size_hint_y=None, height=dp(24)))
        engines = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(46))
        for name, enabled in (("Stockfish", True), ("Built-in", False)):
            ch = Choice(text=name, group="engine", font_size=sp(16),
                        state="down" if enabled == self.game.ai.use_stockfish else "normal")
            ch.bind(on_release=lambda _b, enabled=enabled: sel.__setitem__("stockfish", enabled))
            engines.add_widget(ch)
        sel["stockfish"] = self.game.ai.use_stockfish
        body.add_widget(engines)
        engine_note = Label(
            text="Stockfish is included in supported installers. The game downloads nothing while you play.",
            size_hint_y=None, height=dp(54), halign="left", valign="middle")
        engine_note.bind(size=lambda w, s: setattr(w, "text_size", s))
        body.add_widget(engine_note)

        start = action_button("Start game", size_hint_y=None, height=dp(52), font_size=sp(17))
        body.add_widget(start)

        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(body)
        pop = Popup(title="New game", content=scroll, size_hint=(0.94, 0.9),
                    auto_dismiss=not first)

        def begin(*_):
            pop.dismiss()
            self.flipped = sel["side"] == BLACK
            self.cursor = None
            self.game.new_game(sel["level"], sel["side"], use_stockfish=sel["stockfish"])

        start.bind(on_release=begin)
        self._open(pop)


if __name__ == "__main__":
    ChessApp().run()
