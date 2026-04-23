"""Modal screens for mule-tui — resource picker, help, game over."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from .engine import RESOURCES


class ResourcePickerScreen(ModalScreen[str | None]):
    """Dev-phase modal: pick a resource to outfit a mule for. User lands
    here after pressing 'b' (buy) and before clicking a plot."""

    BINDINGS = [
        Binding("f", "pick('food')", "Food"),
        Binding("e", "pick('energy')", "Energy"),
        Binding("s", "pick('smithore')", "Smithore"),
        Binding("c", "pick('crystite')", "Crystite"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_panel"):
            yield Static("Outfit mule for...", id="modal_title")
            yield Static(
                "[b]f[/b]ood     $20\n"
                "[b]e[/b]nergy   $25\n"
                "[b]s[/b]mithore $30\n"
                "[b]c[/b]rystite $50 (mountain plots only)\n\n"
                "[dim]esc to cancel[/dim]",
            )

    def action_pick(self, resource: str) -> None:
        self.dismiss(resource)

    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape,question_mark,h", "app.pop_screen", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_panel"):
            yield Static("mule-tui — Help", id="modal_title")
            yield Static(
                "Goal: highest total score (gold + property + resources "
                "minus starvation penalty) after 12 rounds.\n\n"
                "[b]Phases per round[/b]:\n"
                "  [yellow]Land Grant[/yellow] — each player gets 1 free plot.\n"
                "  [yellow]Development[/yellow] — buy & place M.U.L.E.s.\n"
                "  [yellow]Production[/yellow] — mules produce resources.\n"
                "  [yellow]Event[/yellow] — random event fires.\n"
                "  [yellow]Auction[/yellow] — surplus is sold at market.\n\n"
                "[b]Controls[/b]:\n"
                "  arrows      — move cursor on map\n"
                "  g           — claim grant plot (land grant phase)\n"
                "  b           — buy + outfit mule (then press plot key)\n"
                "  n           — next phase / end development\n"
                "  p           — pause / resume timer\n"
                "  s           — scoreboard modal\n"
                "  h or ?      — this help\n"
                "  q           — quit\n\n"
                "[dim]esc to close[/dim]",
            )


class ScoresScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape,s", "app.pop_screen", "Close")]

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self._lines = lines

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_panel"):
            yield Static("Scoreboard", id="modal_title")
            yield Static("\n".join(self._lines))
            yield Static("\n[dim]esc to close[/dim]")


class GameOverScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape,enter", "app.pop_screen", "Close"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self._lines = lines

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_panel"):
            yield Static("=== GAME OVER ===", id="modal_title")
            yield Static("\n".join(self._lines))
            yield Static("\n[dim]enter to close, q to quit[/dim]")


class PauseScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape,p,space,enter", "app.pop_screen", "Resume"),
        Binding("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_panel"):
            yield Static("Paused", id="modal_title")
            yield Static("Press [b]p[/b] / space / enter to resume.\n"
                         "Press [b]q[/b] to quit.")
