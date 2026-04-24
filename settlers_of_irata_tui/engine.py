"""settlers-of-irata-tui — clean-room economic sim engine.

GameState holds the 5x9 Irata map, 4 players (1 human + 3 AI), resources,
and round machinery. All decisions derive from the M.U.L.E. public design
writeups — constants and tables here are original.

Phases per round (12 rounds total):
    LAND_GRANT -> DEVELOPMENT -> PRODUCTION -> EVENT -> AUCTION -> (next)

The App drives phase transitions. Engine exposes pure-Python helpers that
are deterministic given a seed — makes QA testing straightforward.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ---- map ----

MAP_W = 9
MAP_H = 5
TOWN_COL = 4          # hub column (every row)

RESOURCES = ("food", "energy", "smithore", "crystite")


class TileKind(str, Enum):
    PLAIN = "plain"
    RIVER = "river"
    MOUNTAIN = "mountain"
    TOWN = "town"


# Base yields per tile kind: (food, energy, smithore, crystite-chance%)
_YIELD: dict[TileKind, tuple[int, int, int, int]] = {
    TileKind.PLAIN:    (2, 3, 1,  0),
    TileKind.RIVER:    (4, 2, 0,  0),
    TileKind.MOUNTAIN: (1, 1, 4, 18),
    TileKind.TOWN:     (0, 0, 0,  0),
}


@dataclass
class Tile:
    x: int
    y: int
    kind: TileKind
    owner: Optional[int] = None          # player index 0..3, or None
    mule_resource: Optional[str] = None  # "food"/"energy"/"smithore"/"crystite"

    @property
    def yields(self) -> tuple[int, int, int, int]:
        return _YIELD[self.kind]

    @property
    def is_town(self) -> bool:
        return self.kind is TileKind.TOWN


def build_map(rng: random.Random) -> list[list[Tile]]:
    """Produce the 5x9 Irata grid.

    Layout idea:
      Row 0: plains with a couple of mountain tiles at the edges.
      Row 1: plains, one mountain corner.
      Row 2: river band (except the town column).
      Row 3: plains.
      Row 4: mountains bottom-left and bottom-right, plains in between.
    Town hub sits at column 4 for all rows (so there's a central street
    running N-S through the map, also a nice hub for the UI).
    """
    grid: list[list[Tile]] = []
    for y in range(MAP_H):
        row: list[Tile] = []
        for x in range(MAP_W):
            if x == TOWN_COL:
                kind = TileKind.TOWN
            elif y == 2:
                kind = TileKind.RIVER
            elif (y == 0 and x in (0, 1, 8)) or (y == 4 and x in (0, 1, 7, 8)):
                kind = TileKind.MOUNTAIN
            elif y == 1 and x == 0:
                kind = TileKind.MOUNTAIN
            elif y == 3 and x == 8:
                kind = TileKind.MOUNTAIN
            else:
                kind = TileKind.PLAIN
            row.append(Tile(x=x, y=y, kind=kind))
        grid.append(row)
    # Randomize a couple of tiles for variation (seeded).
    for _ in range(2):
        x = rng.randrange(MAP_W)
        y = rng.randrange(MAP_H)
        t = grid[y][x]
        if t.kind is TileKind.PLAIN:
            t.kind = TileKind.MOUNTAIN
    return grid


# ---- players ----

RACES = ("mechtron", "flapper", "gollumer", "ugaaite")
# Per-race starting modifiers: (starting_gold, food_need_per_round).
_RACE_START: dict[str, tuple[int, int]] = {
    "mechtron":  (1000, 2),  # mechanical — low food need
    "flapper":   ( 900, 3),
    "gollumer":  ( 800, 3),
    "ugaaite":   (1000, 4),  # hungry
}


@dataclass
class Player:
    idx: int
    name: str
    race: str
    is_human: bool = False
    ai_kind: str = "balanced"   # "balanced" | "greedy" | "defensive"
    gold: int = 1000
    food: int = 4
    energy: int = 4
    smithore: int = 2
    crystite: int = 0
    # Points from food shortfall (tracked for end-game penalty).
    starvation: int = 0

    @property
    def color_key(self) -> str:
        return ("red", "blue", "green", "yellow")[self.idx]

    def food_need(self) -> int:
        return _RACE_START[self.race][1]

    def property_value(self, grid: list[list[Tile]]) -> int:
        v = 0
        for row in grid:
            for t in row:
                if t.owner == self.idx:
                    base = {"plain": 300, "river": 500, "mountain": 400,
                            "town": 0}[t.kind.value]
                    mule = 250 if t.mule_resource else 0
                    v += base + mule
        return v

    def total_score(self, grid: list[list[Tile]]) -> int:
        res_val = (self.food * 25 + self.energy * 30
                   + self.smithore * 40 + self.crystite * 120)
        return self.gold + self.property_value(grid) + res_val - self.starvation * 200


# ---- phases ----

class Phase(Enum):
    LAND_GRANT = auto()
    DEVELOPMENT = auto()
    PRODUCTION = auto()
    EVENT = auto()
    AUCTION = auto()
    GAME_OVER = auto()


PHASE_LABEL: dict[Phase, str] = {
    Phase.LAND_GRANT:   "Land Grant",
    Phase.DEVELOPMENT:  "Development",
    Phase.PRODUCTION:   "Production",
    Phase.EVENT:        "Event",
    Phase.AUCTION:      "Auction",
    Phase.GAME_OVER:    "Game Over",
}


# ---- market ----

@dataclass
class Market:
    """Prices for the auction. Fluctuate each round based on stock."""
    food:     int = 30
    energy:   int = 25
    smithore: int = 50
    crystite: int = 100
    # Per-round demand multipliers (set by events).
    food_mul:     float = 1.0
    energy_mul:   float = 1.0
    smithore_mul: float = 1.0
    crystite_mul: float = 1.0

    def price(self, resource: str) -> int:
        base = getattr(self, resource)
        mul = getattr(self, f"{resource}_mul")
        return max(1, int(base * mul))

    def drift(self, rng: random.Random) -> None:
        """Small random drift each round to keep the market interesting."""
        for r in RESOURCES:
            cur = getattr(self, r)
            step = rng.choice([-3, -1, 0, 1, 1, 3])
            setattr(self, r, max(5, cur + step))


# ---- events ----

EVENTS = [
    ("bonus_shipment",   "Freighter arrives — +2 food all players."),
    ("pirate_raid",      "Pirates strike the richest player: -15% gold."),
    ("earthquake",       "Quake damages a random mountain mule."),
    ("pest_attack",      "Pests eat food in the river belt."),
    ("trade_delegation", "Traders drop in — crystite price doubled."),
    ("solar_flare",      "Solar flare: energy demand +50% next round."),
    ("mule_stampede",    "Wild mules stampede — smithore stock +30%."),
    ("drought",          "Drought — river tiles yield half this round."),
    ("lucky_strike",     "A miner strikes crystite — random player +2 crystite."),
    ("tourist_season",   "Tourist season — food demand +50%."),
]


# ---- core game state ----

@dataclass
class GameState:
    players: list[Player]
    grid: list[list[Tile]]
    market: Market = field(default_factory=Market)
    round: int = 1
    max_rounds: int = 12
    phase: Phase = Phase.LAND_GRANT
    current_player: int = 0     # index into players
    log: list[str] = field(default_factory=list)
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    # DEVELOPMENT-phase timer — soft countdown. If the human doesn't
    # place a mule within this many seconds, the mule "runs away".
    dev_timer: float = 30.0
    last_event: str = ""

    # ---- construction ----

    @classmethod
    def new(cls, human_race: str = "mechtron", seed: int = 1983,
            total_rounds: int = 12) -> "GameState":
        rng = random.Random(seed)
        grid = build_map(rng)
        players: list[Player] = []
        # Human is player 0.
        h_gold = _RACE_START.get(human_race, (1000, 3))[0]
        players.append(Player(
            idx=0, name="You", race=human_race, is_human=True, gold=h_gold,
        ))
        ai_kinds = ["balanced", "greedy", "defensive"]
        ai_races = [r for r in RACES if r != human_race][:3]
        for i, (race, kind) in enumerate(zip(ai_races, ai_kinds), start=1):
            players.append(Player(
                idx=i, name=f"AI-{kind[:3].title()}", race=race,
                is_human=False, ai_kind=kind,
                gold=_RACE_START[race][0],
            ))
        gs = cls(players=players, grid=grid, rng=rng, max_rounds=total_rounds)
        gs.log.append(f"Welcome to Irata — {human_race.title()} colony founded.")
        gs.log.append("Phase: Land Grant (round 1).")
        return gs

    # ---- tile lookup ----

    def tile(self, x: int, y: int) -> Tile:
        return self.grid[y][x]

    def iter_tiles(self):
        for row in self.grid:
            for t in row:
                yield t

    def free_plots(self) -> list[Tile]:
        return [t for t in self.iter_tiles()
                if not t.is_town and t.owner is None]

    def plots_of(self, pidx: int) -> list[Tile]:
        return [t for t in self.iter_tiles() if t.owner == pidx]

    def plots_with_mule_of(self, pidx: int) -> list[Tile]:
        return [t for t in self.iter_tiles()
                if t.owner == pidx and t.mule_resource]

    # ---- phase transitions ----

    def advance_phase(self) -> None:
        """Advance the single shared phase pointer. Returns without error
        at GAME_OVER."""
        if self.phase is Phase.LAND_GRANT:
            self.phase = Phase.DEVELOPMENT
            self.current_player = 0
            self.log.append(
                f"-- Round {self.round}: Development phase --"
            )
        elif self.phase is Phase.DEVELOPMENT:
            self.phase = Phase.PRODUCTION
            self.log.append("-- Production --")
            self.run_production()
        elif self.phase is Phase.PRODUCTION:
            self.phase = Phase.EVENT
            self.run_event()
        elif self.phase is Phase.EVENT:
            self.phase = Phase.AUCTION
            self.run_auction()
        elif self.phase is Phase.AUCTION:
            self.round += 1
            if self.round > self.max_rounds:
                self.phase = Phase.GAME_OVER
                self.log.append("=== GAME OVER ===")
                self.log.append(self.winner_line())
            else:
                self.phase = Phase.LAND_GRANT
                self.market.drift(self.rng)
                # Reset event-driven multipliers.
                self.market.food_mul = 1.0
                self.market.energy_mul = 1.0
                self.market.smithore_mul = 1.0
                self.market.crystite_mul = 1.0
                self.log.append(f"-- Round {self.round}: Land Grant --")
        # GAME_OVER stays stuck.

    # ---- LAND GRANT ----

    def grant_land(self, pidx: int, tx: int, ty: int) -> bool:
        """Give a free plot to player pidx. Returns False if the plot is
        not grantable."""
        t = self.tile(tx, ty)
        if t.is_town or t.owner is not None:
            return False
        t.owner = pidx
        self.log.append(
            f"{self.players[pidx].name} claimed ({tx},{ty}) [{t.kind.value}]."
        )
        return True

    def auto_grant_all(self) -> None:
        """AI + human receive one plot each; in single-player we still
        auto-place the human's first grant of each round on an unclaimed
        tile near their existing holdings (good default). Human can
        re-select later."""
        for p in self.players:
            free = self.free_plots()
            if not free:
                break
            # Prefer a tile adjacent to one they already own if possible.
            mine = self.plots_of(p.idx)
            chosen: Optional[Tile] = None
            if mine:
                for t in free:
                    for m in mine:
                        if abs(t.x - m.x) + abs(t.y - m.y) == 1:
                            chosen = t
                            break
                    if chosen:
                        break
            if chosen is None:
                # First plot of the game — distribute around the map.
                chosen = self.rng.choice(free)
            chosen.owner = p.idx
            self.log.append(
                f"{p.name} received ({chosen.x},{chosen.y}) [{chosen.kind.value}]."
            )

    # ---- DEVELOPMENT ----

    def mule_price(self) -> int:
        """Mule price scales with smithore availability in the common pool.
        Floor 100, ceiling 400."""
        stock = sum(p.smithore for p in self.players)
        return max(100, 400 - stock * 5)

    def outfit_cost(self, resource: str) -> int:
        return {"food": 20, "energy": 25, "smithore": 30, "crystite": 50}[resource]

    def buy_and_place_mule(self, pidx: int, resource: str,
                           tx: int, ty: int) -> tuple[bool, str]:
        """Attempt to buy a mule, outfit for resource, place on tile.
        Returns (success, message)."""
        if resource not in RESOURCES:
            return False, f"unknown resource: {resource!r}"
        t = self.tile(tx, ty)
        if t.is_town:
            return False, "can't place a mule in the town hub."
        if t.owner != pidx:
            return False, "that plot isn't yours."
        if t.mule_resource:
            return False, "that plot already has a mule."
        if resource == "crystite" and t.kind is not TileKind.MOUNTAIN:
            return False, "crystite only on mountain plots."
        p = self.players[pidx]
        total = self.mule_price() + self.outfit_cost(resource)
        if p.gold < total:
            return False, f"not enough gold (need {total}, have {p.gold})."
        p.gold -= total
        t.mule_resource = resource
        self.log.append(
            f"{p.name} bought a mule, outfitted for {resource}, "
            f"placed at ({tx},{ty}). (-{total} gold)"
        )
        return True, "mule placed."

    def ai_develop(self, pidx: int) -> None:
        """AI's turn in development. Place at most one mule."""
        p = self.players[pidx]
        my_plots = [t for t in self.plots_of(pidx) if not t.mule_resource]
        if not my_plots:
            return
        # Strategy: pick resource by AI kind, pick the best yield tile.
        want = {
            "balanced":  ["food", "energy", "smithore", "crystite"],
            "greedy":    ["crystite", "smithore", "energy", "food"],
            "defensive": ["food", "food", "energy", "smithore"],
        }[p.ai_kind]
        # Prefer the resource they haven't produced much of yet.
        want_ordered = sorted(
            RESOURCES,
            key=lambda r: (want.index(r) if r in want else 9,
                           getattr(p, r)),
        )
        for resource in want_ordered:
            # Tile that most benefits this resource.
            if resource == "crystite":
                cand = [t for t in my_plots if t.kind is TileKind.MOUNTAIN]
            elif resource == "food":
                cand = [t for t in my_plots if t.kind in (
                    TileKind.RIVER, TileKind.PLAIN)]
            elif resource == "energy":
                cand = [t for t in my_plots if t.kind is TileKind.PLAIN]
            elif resource == "smithore":
                cand = [t for t in my_plots if t.kind is TileKind.MOUNTAIN]
            else:
                cand = list(my_plots)
            if not cand:
                continue
            # Pick highest-yield candidate.
            def score(t: Tile) -> int:
                f, e, s, _ = t.yields
                return {"food": f, "energy": e, "smithore": s,
                        "crystite": 3 if t.kind is TileKind.MOUNTAIN else 0}[resource]
            cand.sort(key=score, reverse=True)
            ok, _ = self.buy_and_place_mule(pidx, resource, cand[0].x, cand[0].y)
            if ok:
                return

    # ---- PRODUCTION ----

    def run_production(self) -> None:
        """Each mule produces one unit-pack of its resource, scaled by
        plot yield and a small random factor."""
        for t in self.iter_tiles():
            if t.mule_resource is None or t.owner is None:
                continue
            p = self.players[t.owner]
            f_yd, e_yd, s_yd, c_chance = t.yields
            amount = {"food": f_yd, "energy": e_yd,
                      "smithore": s_yd, "crystite": 0}[t.mule_resource]
            # Energy is spent to run non-energy mules. If player is out
            # of energy, yield halves.
            if t.mule_resource != "energy":
                if p.energy > 0:
                    p.energy -= 1
                else:
                    amount = max(1, amount // 2)
            if t.mule_resource == "crystite":
                # 3d6-based: success 18% → 1-3 crystite
                if self.rng.randint(1, 100) <= c_chance:
                    amount = self.rng.randint(1, 3)
                else:
                    amount = 0
            # Final small variance +/-1 for everything else.
            elif amount > 1:
                amount += self.rng.choice([-1, 0, 0, 1])
            amount = max(0, amount)
            setattr(p, t.mule_resource, getattr(p, t.mule_resource) + amount)
            self.log.append(
                f"  {p.name} +{amount} {t.mule_resource} at ({t.x},{t.y})."
            )
        # Starvation check.
        for p in self.players:
            need = p.food_need()
            if p.food < need:
                p.starvation += (need - p.food)
                self.log.append(
                    f"  {p.name} STARVES (-{need - p.food}): "
                    f"had {p.food}/{need} food."
                )
                p.food = 0
            else:
                p.food -= need

    # ---- EVENT ----

    def run_event(self) -> None:
        key, msg = self.rng.choice(EVENTS)
        self.last_event = msg
        self.log.append(f"EVENT: {msg}")
        if key == "bonus_shipment":
            for p in self.players:
                p.food += 2
        elif key == "pirate_raid":
            richest = max(self.players, key=lambda p: p.gold)
            loss = richest.gold * 15 // 100
            richest.gold -= loss
            self.log.append(f"  {richest.name} lost {loss} gold.")
        elif key == "earthquake":
            mules = [t for t in self.iter_tiles()
                     if t.kind is TileKind.MOUNTAIN and t.mule_resource]
            if mules:
                t = self.rng.choice(mules)
                self.log.append(
                    f"  Mule at ({t.x},{t.y}) destroyed."
                )
                t.mule_resource = None
        elif key == "pest_attack":
            affected = []
            for t in self.iter_tiles():
                if t.kind is TileKind.RIVER and t.owner is not None:
                    affected.append(t.owner)
            for pidx in set(affected):
                self.players[pidx].food = max(0, self.players[pidx].food - 2)
        elif key == "trade_delegation":
            self.market.crystite_mul = 2.0
        elif key == "solar_flare":
            self.market.energy_mul = 1.5
        elif key == "mule_stampede":
            for p in self.players:
                p.smithore += max(1, p.smithore // 3)
        elif key == "drought":
            # Handled out-of-band: rerun river tile production halved
            # retroactively would be complex — simpler: penalise current
            # food stocks for river-owners.
            for t in self.iter_tiles():
                if t.kind is TileKind.RIVER and t.owner is not None:
                    self.players[t.owner].food = max(
                        0, self.players[t.owner].food - 1)
        elif key == "lucky_strike":
            p = self.rng.choice(self.players)
            p.crystite += 2
            self.log.append(f"  {p.name} scored +2 crystite.")
        elif key == "tourist_season":
            self.market.food_mul = 1.5

    # ---- AUCTION ----

    def run_auction(self) -> None:
        """Simple deterministic auction — each player tenders surplus
        above a reservation threshold to the store; gold moves."""
        self.log.append("-- Auction --")
        for resource in RESOURCES:
            price = self.market.price(resource)
            for p in self.players:
                have = getattr(p, resource)
                reserve = {
                    "food": max(p.food_need() * 2, 4),
                    "energy": 2,
                    "smithore": 1,
                    "crystite": 0,
                }[resource]
                surplus = have - reserve
                if surplus > 0:
                    # Greedy AIs tender less (hope prices rise); defensive
                    # tender everything surplus.
                    if p.ai_kind == "greedy" and resource != "crystite":
                        surplus = surplus // 2
                    if surplus > 0:
                        revenue = surplus * price
                        setattr(p, resource, have - surplus)
                        p.gold += revenue
                        self.log.append(
                            f"  {p.name} sold {surplus} {resource} "
                            f"@ {price} = +{revenue} gold."
                        )

    # ---- score / winner ----

    def scoreboard(self) -> list[tuple[int, int]]:
        """Sorted list of (player_idx, score), best first."""
        scores = [(p.idx, p.total_score(self.grid)) for p in self.players]
        scores.sort(key=lambda s: -s[1])
        return scores

    def winner_line(self) -> str:
        sb = self.scoreboard()
        winner = self.players[sb[0][0]]
        return f"Winner: {winner.name} ({winner.race}) — score {sb[0][1]}."

    # ---- helpers for UI ----

    def phase_label(self) -> str:
        return PHASE_LABEL[self.phase]

    def current_player_obj(self) -> Player:
        return self.players[self.current_player]
