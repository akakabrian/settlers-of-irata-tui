"""End-to-end playtest for mule-tui via Textual Pilot.

Drives a full interactive flow: boot → pick faction (set via seed) →
land grant → buy mule → install → play a round → quit. Saves SVGs at
each checkpoint to tests/out/playtest_*.svg. Exit 0 on success.

    python -m tests.playtest
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mule_tui.app import MapView, MuleApp
from mule_tui.engine import Phase


OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


async def playtest() -> int:
    app = MuleApp(seed=1983, human_race="mechtron", total_rounds=12)
    async with app.run_test(size=(180, 55)) as pilot:
        await pilot.pause()
        # 1. Boot — on_mount already ran auto_grant + advance to DEVELOPMENT.
        assert app.gs.phase is Phase.DEVELOPMENT, app.gs.phase
        assert app.gs.players[0].race == "mechtron"
        app.save_screenshot(str(OUT / "playtest_01_boot.svg"))

        # 2. Land grant already done by on_mount; verify human has a plot.
        human_plots = app.gs.plots_of(0)
        assert human_plots, "human got no plot on land grant"
        app.save_screenshot(str(OUT / "playtest_02_land_grant.svg"))

        # 3. Buy a mule — position cursor on a human plot, press b, pick food.
        mv = app.query_one(MapView)
        target = human_plots[0]
        mv.cursor_x, mv.cursor_y = target.x, target.y
        gold_before = app.gs.players[0].gold
        await pilot.press("b")
        await pilot.pause()
        # ResourcePickerScreen is now active — press 'f' for food.
        assert app.screen.__class__.__name__ == "ResourcePickerScreen"
        await pilot.press("f")
        await pilot.pause()
        app.save_screenshot(str(OUT / "playtest_03_buy_mule.svg"))

        # 4. Install — buy_and_place_mule ran during 'f' pick; verify.
        assert target.mule_resource == "food", target.mule_resource
        assert app.gs.players[0].gold < gold_before
        app.save_screenshot(str(OUT / "playtest_04_install.svg"))

        # 5. Play a round — advance 4 phases (dev → prod → event → auct → next).
        r0 = app.gs.round
        for _ in range(4):
            await pilot.press("n")
            await pilot.pause()
        assert app.gs.round == r0 + 1, f"round {r0} -> {app.gs.round}"
        app.save_screenshot(str(OUT / "playtest_05_round_complete.svg"))

        # 6. Quit.
        await pilot.press("q")
        await pilot.pause()
    print("playtest: OK  (6 checkpoints saved to tests/out/playtest_*.svg)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(playtest()))
