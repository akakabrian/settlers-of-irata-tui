"""Perf smoke for mule-tui. Checks two hot paths:

  1. Engine: a 12-round deterministic game from GameState.new to GAME_OVER
     using `n`-equivalent phase advances (AI-only, no UI).
  2. UI: MapView.render_line across all 6 rows, 200 iterations.

Budgets are generous (taro is not a perf test rig) — we care about
regressions, not absolute numbers.

    python -m tests.perf
"""

from __future__ import annotations

import asyncio
import sys
import time

from mule_tui.app import MapView, MuleApp
from mule_tui.engine import GameState, Phase


ENGINE_BUDGET_MS = 500        # 12 rounds, all AI, synchronous
RENDER_BUDGET_MS = 250        # 6 rows x 200 iters


def bench_engine() -> float:
    t0 = time.perf_counter()
    gs = GameState.new(seed=42)
    gs.auto_grant_all()
    gs.advance_phase()  # -> DEVELOPMENT
    safety = 0
    while gs.phase is not Phase.GAME_OVER and safety < 200:
        if gs.phase is Phase.DEVELOPMENT:
            for i in range(len(gs.players)):
                gs.ai_develop(i)
        gs.advance_phase()
        if gs.phase is Phase.LAND_GRANT:
            gs.auto_grant_all()
        safety += 1
    elapsed = (time.perf_counter() - t0) * 1000
    assert gs.phase is Phase.GAME_OVER, gs.phase
    return elapsed


async def bench_render() -> float:
    app = MuleApp(seed=42)
    async with app.run_test(size=(180, 55)) as pilot:
        await pilot.pause()
        mv = app.query_one(MapView)
        t0 = time.perf_counter()
        for _ in range(200):
            for y in range(6):
                mv.render_line(y)
        return (time.perf_counter() - t0) * 1000


async def main() -> int:
    eng_ms = bench_engine()
    render_ms = await bench_render()
    ok_engine = eng_ms < ENGINE_BUDGET_MS
    ok_render = render_ms < RENDER_BUDGET_MS
    mark = lambda b: "\033[32mOK\033[0m" if b else "\033[31mSLOW\033[0m"
    print(f"  engine 12-round full game: {eng_ms:6.1f}ms "
          f"(budget {ENGINE_BUDGET_MS}ms) {mark(ok_engine)}")
    print(f"  render 6rows x 200 iters : {render_ms:6.1f}ms "
          f"(budget {RENDER_BUDGET_MS}ms) {mark(ok_render)}")
    return 0 if (ok_engine and ok_render) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
