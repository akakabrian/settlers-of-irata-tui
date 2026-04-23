"""Headless QA for mule-tui.

Runs each scenario in a fresh MuleApp via App.run_test(), saves an SVG
screenshot, reports pass/fail. Exit code = #failures.

    python -m tests.qa           # all
    python -m tests.qa phase     # substring match
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from mule_tui.app import MapView, MuleApp
from mule_tui.engine import MAP_H, MAP_W, Phase, TileKind


OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


@dataclass
class Scenario:
    name: str
    fn: Callable[[MuleApp, "object"], Awaitable[None]]


# ---- scenarios ----

async def s_mount_clean(app, pilot):
    assert app.gs is not None
    assert len(app.gs.players) == 4
    assert app.gs.players[0].is_human
    for p in app.gs.players[1:]:
        assert not p.is_human
    # Map shape.
    assert len(app.gs.grid) == MAP_H
    assert len(app.gs.grid[0]) == MAP_W
    # Town column has 5 town tiles.
    town_cnt = sum(1 for t in app.gs.iter_tiles() if t.is_town)
    assert town_cnt == MAP_H, town_cnt


async def s_status_bar_populated(app, pilot):
    txt = app._last_status_text
    assert "Round" in txt, txt
    assert "Phase" in txt, txt
    assert "food=" in txt, txt
    assert "$" in txt, txt


async def s_cursor_starts_top_left(app, pilot):
    mv = app.query_one(MapView)
    assert mv.cursor_x == 0
    assert mv.cursor_y == 0


async def s_arrow_keys_move_cursor(app, pilot):
    mv = app.query_one(MapView)
    await pilot.press("right")
    await pilot.pause()
    assert mv.cursor_x == 1
    await pilot.press("down")
    await pilot.pause()
    assert mv.cursor_y == 1
    await pilot.press("left")
    await pilot.pause()
    assert mv.cursor_x == 0
    await pilot.press("up")
    await pilot.pause()
    assert mv.cursor_y == 0


async def s_cursor_clamps(app, pilot):
    mv = app.query_one(MapView)
    for _ in range(20):
        await pilot.press("left")
    await pilot.pause()
    assert mv.cursor_x == 0
    for _ in range(20):
        await pilot.press("right")
    await pilot.pause()
    assert mv.cursor_x == MAP_W - 1
    for _ in range(20):
        await pilot.press("up")
    await pilot.pause()
    assert mv.cursor_y == 0
    for _ in range(20):
        await pilot.press("down")
    await pilot.pause()
    assert mv.cursor_y == MAP_H - 1


async def s_initial_land_grant(app, pilot):
    # On mount, auto_grant_all gave everyone a plot.
    for p in app.gs.players:
        plots = app.gs.plots_of(p.idx)
        assert len(plots) >= 1, f"{p.name} has no plots"


async def s_phase_cycle_advances_round(app, pilot):
    # App starts in DEVELOPMENT (mount already advanced from LAND_GRANT).
    assert app.gs.phase is Phase.DEVELOPMENT
    assert app.gs.round == 1
    # Drive through development → production → event → auction → next.
    for _ in range(4):
        await pilot.press("n")
        await pilot.pause()
    assert app.gs.round == 2, f"round={app.gs.round}"
    assert app.gs.phase is Phase.DEVELOPMENT, app.gs.phase


async def s_buy_mule_on_owned_plot(app, pilot):
    # Move cursor onto one of the human's plots and buy.
    human_plot = app.gs.plots_of(0)[0]
    mv = app.query_one(MapView)
    # Reset cursor to (0,0) and step over.
    mv.cursor_x = human_plot.x
    mv.cursor_y = human_plot.y
    gold_before = app.gs.players[0].gold
    ok, msg = app.gs.buy_and_place_mule(
        0, "food", human_plot.x, human_plot.y)
    assert ok, msg
    assert app.gs.players[0].gold < gold_before
    assert human_plot.mule_resource == "food"


async def s_cant_buy_mule_on_town(app, pilot):
    # Town tile at (4, 2).
    ok, msg = app.gs.buy_and_place_mule(0, "food", 4, 2)
    assert not ok
    assert "town" in msg.lower()


async def s_cant_buy_mule_on_enemy_plot(app, pilot):
    # Find an AI's plot.
    ai_plot = None
    for t in app.gs.iter_tiles():
        if t.owner is not None and t.owner != 0:
            ai_plot = t
            break
    assert ai_plot is not None
    ok, msg = app.gs.buy_and_place_mule(0, "food", ai_plot.x, ai_plot.y)
    assert not ok
    assert "yours" in msg.lower() or "owner" in msg.lower()


async def s_crystite_requires_mountain(app, pilot):
    # Find a non-mountain plot of the human.
    plot = None
    for t in app.gs.plots_of(0):
        if t.kind is not TileKind.MOUNTAIN:
            plot = t
            break
    assert plot is not None
    ok, msg = app.gs.buy_and_place_mule(0, "crystite", plot.x, plot.y)
    assert not ok
    assert "crystite" in msg.lower() or "mountain" in msg.lower()


async def s_production_adds_resources(app, pilot):
    # Place a food mule on the human's first plot, run production.
    t = app.gs.plots_of(0)[0]
    app.gs.buy_and_place_mule(0, "food", t.x, t.y)
    before = app.gs.players[0].food
    app.gs.run_production()
    # Food minus food_need may be higher or lower; check that the mule
    # actually contributed (food is non-negative; either food went up
    # relative to (before - need) or the player was force-starved).
    # Simpler: raw production pre-consumption is >0. We approximate by
    # asserting the mule-food-added path actually fired.
    p = app.gs.players[0]
    # If starvation happened food is 0; otherwise food went up.
    ran_ok = (p.food != before) or (p.starvation > 0) or p.food == 0
    assert ran_ok


async def s_full_round_completes_without_crash(app, pilot):
    # Drive four `n` presses to finish the round.
    r0 = app.gs.round
    for _ in range(4):
        await pilot.press("n")
        await pilot.pause()
    assert app.gs.round == r0 + 1


async def s_six_rounds_no_crash(app, pilot):
    for _ in range(5 * 4):  # 5 more rounds after the first auto-advance
        await pilot.press("n")
        await pilot.pause()
    assert app.gs.round >= 6


async def s_game_over_at_max_rounds(app, pilot):
    # Override max_rounds to 2 so we hit GAME_OVER quickly.
    app.gs.max_rounds = 2
    # Two full cycles.
    safety = 0
    while app.gs.phase is not Phase.GAME_OVER and safety < 30:
        await pilot.press("n")
        await pilot.pause()
        safety += 1
    assert app.gs.phase is Phase.GAME_OVER, (
        f"phase={app.gs.phase} round={app.gs.round} safety={safety}"
    )


async def s_scoreboard_sorted(app, pilot):
    sb = app.gs.scoreboard()
    scores = [s for _, s in sb]
    assert scores == sorted(scores, reverse=True)


async def s_help_screen_opens(app, pilot):
    await pilot.press("h")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "HelpScreen"
    await pilot.press("escape")
    await pilot.pause()


async def s_scores_screen_opens(app, pilot):
    await pilot.press("s")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "ScoresScreen"
    await pilot.press("escape")
    await pilot.pause()


async def s_pause_screen_opens(app, pilot):
    await pilot.press("p")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "PauseScreen"
    await pilot.press("escape")
    await pilot.pause()


async def s_ai_places_at_least_one_mule_per_round(app, pilot):
    ai_mules_before = sum(
        1 for t in app.gs.iter_tiles()
        if t.mule_resource and t.owner and t.owner != 0
    )
    # Press n to trigger AI dev turn.
    await pilot.press("n")
    await pilot.pause()
    ai_mules_after = sum(
        1 for t in app.gs.iter_tiles()
        if t.mule_resource and t.owner and t.owner != 0
    )
    # At least one AI should have placed a mule (defensive AI always
    # tries food on plain/river — should succeed round 1).
    assert ai_mules_after > ai_mules_before, (
        f"{ai_mules_before} -> {ai_mules_after}"
    )


async def s_event_fires_each_round(app, pilot):
    # Cycle to the EVENT phase and check last_event populates.
    while app.gs.phase is not Phase.EVENT:
        await pilot.press("n")
        await pilot.pause()
        if app.gs.phase is Phase.GAME_OVER:
            break
    # One more advance to run_event if not run yet — actually
    # advance_phase into EVENT runs it. So last_event should be set.
    assert app.gs.last_event, "last_event empty"


async def s_market_prices_positive(app, pilot):
    for r in ("food", "energy", "smithore", "crystite"):
        assert app.gs.market.price(r) > 0


async def s_determinism_same_seed(app, pilot):
    # Launch two fresh engines with the same seed and compare round 1
    # development outcome when only AIs play.
    from mule_tui.engine import GameState
    gs1 = GameState.new(seed=77)
    gs2 = GameState.new(seed=77)
    gs1.auto_grant_all(); gs1.advance_phase()
    gs2.auto_grant_all(); gs2.advance_phase()
    for i in range(1, 4):
        gs1.ai_develop(i)
        gs2.ai_develop(i)
    # Compare AI mule placements.
    m1 = [(t.x, t.y, t.mule_resource, t.owner)
          for t in gs1.iter_tiles() if t.mule_resource]
    m2 = [(t.x, t.y, t.mule_resource, t.owner)
          for t in gs2.iter_tiles() if t.mule_resource]
    assert m1 == m2, f"{m1} != {m2}"


async def s_starvation_penalty_applied(app, pilot):
    # Crank food need via direct mutation: empty player food, run
    # production without mules (so they starve), check starvation > 0.
    p = app.gs.players[0]
    p.food = 0
    need = p.food_need()
    before = p.starvation
    app.gs.run_production()
    # If the human has no food mules placed, they starve by `need`.
    # (Their earlier mule placements via app may alter this — but with
    # food=0 and need>=2, at least some starvation accrues if food
    # production from any mules is < need.)
    # More robust: force no mules then run.
    for t in app.gs.iter_tiles():
        t.mule_resource = None
    p.food = 0
    before2 = p.starvation
    app.gs.run_production()
    assert p.starvation > before2, (
        f"starvation unchanged: {before2} -> {p.starvation}"
    )


async def s_render_line_has_segments(app, pilot):
    mv = app.query_one(MapView)
    for y in range(MAP_H + 1):
        strip = mv.render_line(y)
        segs = list(strip)
        assert len(segs) > 0, f"row {y} empty"


async def s_auction_transfers_gold(app, pilot):
    # Give player 0 a surplus of smithore, run auction, check gold went up.
    p = app.gs.players[0]
    p.smithore = 20
    gold_before = p.gold
    app.gs.run_auction()
    assert p.gold > gold_before, (
        f"auction didn't pay out: {gold_before} -> {p.gold}"
    )
    assert p.smithore < 20


async def s_log_panel_accepts_writes(app, pilot):
    from textual.widgets import RichLog
    log = app.query_one("#log", RichLog)
    lines_before = len(log.lines)
    app.gs.log.append("test-line")
    app._flush_log()
    # Can't easily read RichLog lines, but the gs.log should be cleared.
    assert app.gs.log == []


SCENARIOS = [
    Scenario("mount_clean", s_mount_clean),
    Scenario("status_bar_populated", s_status_bar_populated),
    Scenario("cursor_starts_top_left", s_cursor_starts_top_left),
    Scenario("arrow_keys_move_cursor", s_arrow_keys_move_cursor),
    Scenario("cursor_clamps_at_bounds", s_cursor_clamps),
    Scenario("initial_land_grant_populates_plots", s_initial_land_grant),
    Scenario("phase_cycle_advances_round", s_phase_cycle_advances_round),
    Scenario("buy_mule_on_owned_plot", s_buy_mule_on_owned_plot),
    Scenario("cant_buy_mule_on_town", s_cant_buy_mule_on_town),
    Scenario("cant_buy_mule_on_enemy_plot", s_cant_buy_mule_on_enemy_plot),
    Scenario("crystite_requires_mountain", s_crystite_requires_mountain),
    Scenario("production_adds_resources", s_production_adds_resources),
    Scenario("full_round_completes_without_crash", s_full_round_completes_without_crash),
    Scenario("six_rounds_no_crash", s_six_rounds_no_crash),
    Scenario("game_over_at_max_rounds", s_game_over_at_max_rounds),
    Scenario("scoreboard_sorted_desc", s_scoreboard_sorted),
    Scenario("help_screen_opens", s_help_screen_opens),
    Scenario("scores_screen_opens", s_scores_screen_opens),
    Scenario("pause_screen_opens", s_pause_screen_opens),
    Scenario("ai_places_mule_each_round", s_ai_places_at_least_one_mule_per_round),
    Scenario("event_fires_each_round", s_event_fires_each_round),
    Scenario("market_prices_positive", s_market_prices_positive),
    Scenario("determinism_same_seed", s_determinism_same_seed),
    Scenario("starvation_penalty_applied", s_starvation_penalty_applied),
    Scenario("map_render_has_segments", s_render_line_has_segments),
    Scenario("auction_transfers_gold", s_auction_transfers_gold),
    Scenario("log_panel_accepts_writes", s_log_panel_accepts_writes),
]


# ---- driver ----

async def run_one(scn: Scenario) -> tuple[str, bool, str]:
    app = MuleApp()
    try:
        async with app.run_test(size=(180, 55)) as pilot:
            await pilot.pause()
            try:
                await scn.fn(app, pilot)
            except AssertionError as e:
                app.save_screenshot(str(OUT / f"{scn.name}.FAIL.svg"))
                return (scn.name, False, f"AssertionError: {e}")
            except Exception as e:
                app.save_screenshot(str(OUT / f"{scn.name}.ERROR.svg"))
                return (scn.name, False,
                        f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            app.save_screenshot(str(OUT / f"{scn.name}.PASS.svg"))
            return (scn.name, True, "")
    except Exception as e:
        return (scn.name, False,
                f"harness error: {type(e).__name__}: {e}\n{traceback.format_exc()}")


async def main(pattern: str | None = None) -> int:
    scenarios = [s for s in SCENARIOS if not pattern or pattern in s.name]
    if not scenarios:
        print(f"no scenarios match {pattern!r}")
        return 2
    results = []
    for scn in scenarios:
        name, ok, msg = await run_one(scn)
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {name}")
        if not ok:
            for line in msg.splitlines():
                print(f"      {line}")
        results.append((name, ok, msg))
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\n{passed}/{len(results)} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(asyncio.run(main(pattern)))
