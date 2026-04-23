# mule-tui

Terminal-native, clean-room Python port of the classic 1983 4-player
economic sim set on the planet Irata.

**Not affiliated** with the original publishers. Re-implementation from
public design writeups — see `DECISIONS.md` for provenance.

## Quick start

```
make all        # set up venv + install
make run        # play
make test       # run the QA suite
```

## Controls

- `arrows` — move cursor on the 5×9 map
- `g` — claim the highlighted plot (Land Grant phase)
- `b` — buy + outfit + place a M.U.L.E. (Development phase)
- `n` — advance to the next phase (also runs AI turns)
- `p` — pause
- `s` — scoreboard
- `h` or `?` — help
- `q` — quit

You play **Player 1** (the Mechtron by default). Three AIs with
different policies (balanced / greedy / defensive) round out the table.
Highest score after 12 rounds wins.

## Design notes

See `DECISIONS.md` for:
- why Pattern 4 (clean-room Python) instead of a vendored engine;
- map layout (5×9 with central town hub, river band, mountain
  clusters);
- race starting stats and food needs;
- yield tables per tile kind;
- event effects.

## Tests

```
make test              # all 27 scenarios
make test-only PAT=buy # subset by substring
```

Screenshots of every scenario land in `tests/out/*.svg`.
