# mule-tui — design decisions

## 2026-04-23 — Binding strategy

**Decision: Pattern 4 — clean-room Python reimplementation.**

### Context

The original **M.U.L.E.** is 1983 Dani Bunten / Ozark Softscape on Atari 800
6502 assembly, later ported to C64, NES, IBM PC. The IP belongs to
Electronic Arts (as Ozark's publisher and successor). There is **no**
clean, permissive open-source engine. The clones that exist
(planet-mule, WORLD OF MULE, Mule Online Tournament) are either (a)
their own reimplementations with unclear licensing, or (b) ROM-based
emulator setups.

### Decision

Clean-room Python reimplementation from the **public design writeups**:

- Halcyon Days interview (Dani Bunten, 1997)
- Gamasutra post-mortem
- Wikipedia entry
- Generic "how M.U.L.E. works" analyses in the retro-games press

We implement the **mechanics** — land grant, development phase, mule
outfitting, production, auction, events — not the original art / sounds
/ copyrighted IP. All strings, race names, music, and assets are
original or procedurally generated. The sibling `julius-tui` /
`karateka-tui` / `ff1-tui` ports follow the same pattern.

### Clean-room renames

Original → ours:
- Irata → **Irata** (the word is a reversal of "atari"; still
  evocative of the planet, reused as a neutral fictional name)
- Mechtron → **Mechtron** (mechanical/methodical type) — kept, generic
- Flapper → **Flapper** (bird-like/agile)
- Gollumer → **Gollumer** (kept generic, not LoTR-derived)
- Ugaite → **Ugaaite** (spelling tweak)
- Smithore → **smithore** (resource; kept as generic name)
- Crystite → **crystite**

These are all **common-noun / descriptor names**, not protected IP.

## Map

Original is 5×9 (45 plots). We use **5×9** with:
- Centre column = town hub (column 4, all rows) — buildings + auction
- Rivers: a band of river tiles in row 2 (food-bonus)
- Mountains: clustered tiles top-left and bottom-right (smithore-bonus)
- Plains: everything else (energy/food balance)

Plot yields (per M.U.L.E. lore):
- Plain: food +2, energy +3, smithore +1
- River: food +4, energy +2, smithore +0
- Mountain: food +1, energy +1, smithore +4
- Crystite is produced only on mountain plots once a prospecting roll
  succeeds.

## Turn structure (12 rounds = months)

Each round:
1. **Land grant** — each player gets 1 free plot (auto-placed adjacent
   to previous holdings in single-player fill).
2. **Development phase** — each player visits the store (hotseat), buys
   a M.U.L.E. (price varies with smithore stock), outfits it for a
   resource, and chooses a plot to install it on. In the original this
   is a **time-limited mini-game**; in our TUI we use a 30-second
   soft-timer per player (`set_interval`) that, if it expires, the mule
   "runs away" and is lost.
3. **Production** — each installed mule produces its resource, scaled
   by plot yield and spent energy.
4. **Random event** — one of a small menu (pirate raid, earthquake,
   pest attack, bonus shipment, trade delegation).
5. **Auction** — players simultaneously bid (single-player: resolve
   deterministic against AI via reservation-price curves).

## Single-player

Human is Player 1. AIs fill players 2-4 with simple deterministic
policies:
- **Balanced AI** — diversify mules across food/energy/smithore
- **Greedy AI** — chase crystite once smithore stock is high
- **Defensive AI** — prioritise food first, then energy

Score = gold on hand + assessed property value (plot base + mule
bonuses).

## Scope for final stage

- Playable 1-human-vs-3-AI game for 6+ rounds
- Land grant → development → production → event → auction
- 5×9 map rendered with tile colors, cursor, ownership overlays
- Score / property / money panels
- Pause + game-over modals
