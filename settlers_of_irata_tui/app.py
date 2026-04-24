"""settlers-of-irata-tui — Textual app layering the clean-room engine.

Layout:
    ┌ status bar ────────────────────────────────────────────────────┐
    │ Round 3/12 • Phase: Development • You: $1280  food=5 energy=2  │
    ├ map panel ────────────┬ scores / actions / log ────────────────┤
    │                       │ Scores (bar graph + totals)            │
    │  5x9 Irata grid       ├────────────────────────────────────────┤
    │  cursor, ownership,   │ Actions (context-sensitive help)       │
    │  mule overlays        ├────────────────────────────────────────┤
    │                       │ Log (RichLog, auto-scroll)             │
    └───────────────────────┴────────────────────────────────────────┘

The App drives phase transitions via single-key actions. The human plays
player 0; AIs play deterministically when the phase advances into their
slot.
"""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Footer, Header, RichLog, Static

from . import tiles
from .engine import (
    MAP_H,
    MAP_W,
    RESOURCES,
    GameState,
    Phase,
    TileKind,
)
from .screens import (
    GameOverScreen,
    HelpScreen,
    PauseScreen,
    ResourcePickerScreen,
    ScoresScreen,
)


# Each tile renders as a 3-char wide cell: "[G ]" with G = tile glyph,
# optional mule resource letter in the middle row, bracketed by the
# owner's color on a dark background. Keeping cells fixed-width lets us
# compute cursor coords from widget coords cleanly.
CELL_W = 3
CELL_H = 1


class MapView(Widget):
    """Renders the 5x9 Irata grid with cursor + ownership overlays."""

    cursor_x = reactive(0)
    cursor_y = reactive(0)

    DEFAULT_CSS = ""

    def __init__(self, gs: GameState) -> None:
        super().__init__(id="mapview")
        self.gs = gs

    def on_mount(self) -> None:
        # Fit the widget to exactly MAP_W * CELL_W cols and MAP_H rows
        # plus 1 for a header. Textual sizes on content when these are
        # set; safer than relying on container ratios.
        self.styles.width = MAP_W * CELL_W + 2
        self.styles.height = MAP_H + 1

    def render_line(self, y: int) -> Strip:
        if y == 0:
            # Column header — x coords.
            header = "  "
            for x in range(MAP_W):
                header += f"{x:>2} "
            return Strip(
                [Segment(header, Style.parse("bold rgb(170,160,220)"))]
            )
        ty = y - 1
        if ty < 0 or ty >= MAP_H:
            return Strip.blank(self.size.width)
        segs: list[Segment] = [
            Segment(f"{ty} ", Style.parse("bold rgb(170,160,220)")),
        ]
        for x in range(MAP_W):
            t = self.gs.tile(x, ty)
            glyph = tiles.tile_glyph(t.kind, x, ty)
            style = tiles.tile_style(t.kind, t.owner)
            cell_text = f" {glyph} "
            if t.mule_resource:
                letter = tiles.RESOURCE_GLYPH[t.mule_resource]
                cell_text = f"[{letter}]"
                style = tiles.mule_style(t.owner if t.owner is not None else 0)
            # Cursor highlight overrides.
            if x == self.cursor_x and ty == self.cursor_y:
                cell_text = f">{cell_text[1]}<"
                style = Style.parse(
                    "bold rgb(255,255,120) on rgb(80,60,20)")
            segs.append(Segment(cell_text, style))
        return Strip(segs)


class ScoresPanel(Static):
    def __init__(self, gs: GameState) -> None:
        super().__init__("", id="scores_panel")
        self.gs = gs

    def refresh_panel(self) -> None:
        lines = ["[b]Scores[/b]"]
        sb = self.gs.scoreboard()
        for idx, score in sb:
            p = self.gs.players[idx]
            color = tiles.PLAYER_COLORS[idx]
            tag = "(YOU) " if p.is_human else ""
            lines.append(
                f"[{color}]{p.name:<10}[/] {tag}${p.gold:<5} "
                f"prop=${p.property_value(self.gs.grid):<5} "
                f"= [b]{score}[/b]"
            )
            lines.append(
                f"  f={p.food} e={p.energy} s={p.smithore} c={p.crystite} "
                f"(need food {p.food_need()})"
            )
        self.update("\n".join(lines))


class ActionsPanel(Static):
    def __init__(self, gs: GameState) -> None:
        super().__init__("", id="actions_panel")
        self.gs = gs

    def refresh_panel(self) -> None:
        lines = [f"[b]Phase:[/b] [yellow]{self.gs.phase_label()}[/]"]
        if self.gs.phase is Phase.LAND_GRANT:
            lines += [
                "[dim]Arrows move cursor[/dim]",
                "[b]g[/b]  claim the highlighted plot",
                "[b]n[/b]  auto-grant everyone + advance",
                "[b]s[/b]  scores   [b]h[/b] help   [b]q[/b] quit",
            ]
        elif self.gs.phase is Phase.DEVELOPMENT:
            who = self.gs.current_player_obj()
            tag = "YOUR TURN" if who.is_human else f"{who.name} thinking..."
            lines += [
                f"Active: {tag}",
                f"Mule price: ${self.gs.mule_price()}",
                "[b]b[/b]  buy + outfit + place on cursor plot",
                "[b]n[/b]  end turn (or auto-advance AIs)",
                "[b]s[/b]  scores   [b]h[/b] help",
            ]
        elif self.gs.phase in (Phase.PRODUCTION, Phase.EVENT, Phase.AUCTION):
            lines += [
                "Resolving phase...",
                "[b]n[/b]  continue to next phase",
                f"Last event: [i]{self.gs.last_event or '-'}[/i]",
            ]
        elif self.gs.phase is Phase.GAME_OVER:
            lines += [
                "[b]GAME OVER[/b]",
                self.gs.winner_line(),
                "[b]s[/b]  scores   [b]q[/b] quit",
            ]
        self.update("\n".join(lines))


class MuleApp(App):
    """Main app."""

    CSS_PATH = "tui.tcss"
    TITLE = "settlers-of-irata-tui"

    BINDINGS = [
        Binding("up",    "move(0,-1)", "↑", show=False, priority=True),
        Binding("down",  "move(0, 1)", "↓", show=False, priority=True),
        Binding("left",  "move(-1,0)", "←", show=False, priority=True),
        Binding("right", "move(1, 0)", "→", show=False, priority=True),
        Binding("g", "grant", "Grant"),
        Binding("b", "buy_mule", "Buy"),
        Binding("n", "next_phase", "Next"),
        Binding("p", "pause", "Pause"),
        Binding("s", "scores", "Scores"),
        Binding("h", "help", "Help"),
        Binding("question_mark", "help", "Help", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, seed: int = 1983, human_race: str = "mechtron",
                 total_rounds: int = 12) -> None:
        super().__init__()
        self.gs = GameState.new(
            human_race=human_race, seed=seed, total_rounds=total_rounds,
        )
        self._last_status_text: str = ""

    # ---- compose ----

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("", id="status_bar")
        with Horizontal(id="body"):
            with Vertical(id="map_panel"):
                yield MapView(self.gs)
            with Vertical(id="side"):
                yield ScoresPanel(self.gs)
                yield ActionsPanel(self.gs)
                with Vertical(id="log_panel"):
                    yield RichLog(id="log", max_lines=500, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        # Give the human their starting plot on round 1 land grant.
        self.gs.auto_grant_all()
        self.gs.advance_phase()  # -> DEVELOPMENT
        self.refresh_all()
        # Idle AI auto-play happens when the user presses `n` — simpler
        # than doing it on a timer for the initial scaffold.

    # ---- helpers ----

    def refresh_all(self) -> None:
        mv = self.query_one(MapView)
        mv.refresh()
        self.query_one(ScoresPanel).refresh_panel()
        self.query_one(ActionsPanel).refresh_panel()
        self._update_status_bar()
        self._flush_log()

    def _update_status_bar(self) -> None:
        p = self.gs.players[0]
        txt = (
            f"Round {self.gs.round}/{self.gs.max_rounds} • "
            f"Phase: {self.gs.phase_label()} • "
            f"You: ${p.gold}  food={p.food}  energy={p.energy}  "
            f"smithore={p.smithore}  crystite={p.crystite}"
        )
        self._last_status_text = txt
        self.query_one("#status_bar", Static).update(txt)

    def _flush_log(self) -> None:
        log = self.query_one("#log", RichLog)
        # Only write lines we haven't written yet. We approximate by
        # writing any engine-log line once per frame, then clearing the
        # engine-side queue. Simpler: append all, then truncate.
        if self.gs.log:
            for line in self.gs.log:
                log.write(line)
            self.gs.log.clear()

    # ---- actions ----

    def action_move(self, dx: int, dy: int) -> None:
        mv = self.query_one(MapView)
        nx = max(0, min(MAP_W - 1, mv.cursor_x + dx))
        ny = max(0, min(MAP_H - 1, mv.cursor_y + dy))
        mv.cursor_x = nx
        mv.cursor_y = ny
        mv.refresh()

    def action_grant(self) -> None:
        if self.gs.phase is not Phase.LAND_GRANT:
            self.gs.log.append("grant only in Land Grant phase.")
            self.refresh_all()
            return
        mv = self.query_one(MapView)
        ok = self.gs.grant_land(0, mv.cursor_x, mv.cursor_y)
        if not ok:
            self.gs.log.append("can't claim that tile.")
        self.refresh_all()

    def action_buy_mule(self) -> None:
        if self.gs.phase is not Phase.DEVELOPMENT:
            self.gs.log.append("buy only in Development phase.")
            self.refresh_all()
            return
        if not self.gs.current_player_obj().is_human:
            self.gs.log.append("wait for your turn (press n to advance AIs).")
            self.refresh_all()
            return
        mv = self.query_one(MapView)
        cx, cy = mv.cursor_x, mv.cursor_y

        def on_pick(resource: str | None) -> None:
            if resource is None:
                self.gs.log.append("mule purchase cancelled.")
                self.refresh_all()
                return
            ok, msg = self.gs.buy_and_place_mule(0, resource, cx, cy)
            self.gs.log.append(msg if not ok else f"placed: {msg}")
            self.refresh_all()

        self.push_screen(ResourcePickerScreen(), on_pick)

    def action_next_phase(self) -> None:
        """Context-sensitive advance. Land grant: skip to Development.
        Development: run AIs, then advance. Other phases: advance."""
        if self.gs.phase is Phase.LAND_GRANT:
            # Ensure human got a plot too; otherwise auto-place.
            human_plots = [t for t in self.gs.iter_tiles() if t.owner == 0]
            if not human_plots:
                mv = self.query_one(MapView)
                self.gs.grant_land(0, mv.cursor_x, mv.cursor_y)
            self.gs.advance_phase()
        elif self.gs.phase is Phase.DEVELOPMENT:
            # Run every AI's dev turn, then advance.
            for pidx in range(1, len(self.gs.players)):
                self.gs.current_player = pidx
                self.gs.ai_develop(pidx)
            self.gs.advance_phase()  # -> PRODUCTION (runs production internally)
        elif self.gs.phase is Phase.PRODUCTION:
            self.gs.advance_phase()  # -> EVENT
        elif self.gs.phase is Phase.EVENT:
            self.gs.advance_phase()  # -> AUCTION
        elif self.gs.phase is Phase.AUCTION:
            self.gs.advance_phase()  # -> LAND_GRANT next round (or GAME_OVER)
            if self.gs.phase is Phase.LAND_GRANT:
                # Auto-grant a plot for next round's opening.
                self.gs.auto_grant_all()
                self.gs.advance_phase()  # -> DEVELOPMENT
        self.refresh_all()
        if self.gs.phase is Phase.GAME_OVER:
            self._show_game_over()

    def action_pause(self) -> None:
        self.push_screen(PauseScreen())

    def action_scores(self) -> None:
        sb = self.gs.scoreboard()
        lines = []
        for idx, score in sb:
            p = self.gs.players[idx]
            lines.append(
                f"{p.name:<10} ({p.race}) ${p.gold:<5} "
                f"prop=${p.property_value(self.gs.grid):<5} "
                f"f={p.food} e={p.energy} s={p.smithore} c={p.crystite} "
                f"→ {score}"
            )
        self.push_screen(ScoresScreen(lines))

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    # ---- internal ----

    def _show_game_over(self) -> None:
        sb = self.gs.scoreboard()
        lines = [self.gs.winner_line(), ""]
        for rank, (idx, score) in enumerate(sb, start=1):
            p = self.gs.players[idx]
            lines.append(f"{rank}. {p.name:<10} ({p.race:<9}) {score}")
        self.push_screen(GameOverScreen(lines))
