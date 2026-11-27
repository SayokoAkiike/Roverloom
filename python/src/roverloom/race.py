"""Experimental kart-style rover race: laps, NPC rivals, ghosts, a local leaderboard and agents.

These are game rules, separate from the scored mission benchmark (ADR 0018). Speeds, boosts,
dust and battery values are invented game settings, not rover or Martian measurements.
"""

from __future__ import annotations

import contextlib
import hashlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from roverloom.contract import ContractError, JsonDict, dump_json, load_json_file
from roverloom.rally import PAINTS, garage, stats

RULESET = "race-0.1"
MODEL_VERSION = "race-drive-0.1"  # NPC and headless kinematics, not Unreal physics
AGENT_PROTOCOL = "race-agent-1"
MAX_SPEED_MPS = 0.5  # pathfinder_6w limits, as RoverDrive.h
MAX_YAW_RADPS = 0.4918
ACCEL_MPS2 = 0.5
TICK_S = 0.1
COUNTDOWN_S = 3.0
BOOST_S = 3.0
BOOST_SCALE = 1.5
MAX_BOOSTS = 3
PAD_COOLDOWN_S = 6.0
DIFFICULTIES = {"easy": (0.0, 0.78), "standard": (0.2, 0.9), "hard": (0.4, 0.98)}
COLORS = {
    "ivory": (0.8, 0.76, 0.62),
    "cyan": (0.12, 0.65, 0.75),
    "orange": (0.9, 0.3, 0.08),
    "slate": (0.32, 0.36, 0.4),
    "gold": (0.85, 0.62, 0.18),
    "teal": (0.1, 0.45, 0.42),
}


@dataclass(frozen=True)
class Course:
    """Gates in order. Without `start_point` it is a loop whose last gate is the start and finish.

    `line` is a drivable path through every gate, for NPCs, the minimap and the markers. On the
    Gale courses it was routed on the HiRISE heightfield under a 10 degree slope limit
    (docs/race.md).
    """

    id: str
    name: str
    checkpoints: tuple[tuple[float, float], ...]
    sand: tuple[tuple[float, float, float, float], ...] = ()
    pads: tuple[tuple[float, float], ...] = ()
    supply: tuple[float, float] | None = None
    gate_radius_m: float = 2.5
    laps: int = 2
    limit_s: float = 600.0
    start_point: tuple[float, float] | None = None
    line: tuple[tuple[float, float], ...] = ()
    ground: str = "generated"  # or "gale": needs the Gale level
    style: str = "gates"  # or "flags": golf-style flags
    drain_scale: float = 1.0  # battery drain, so that long courses can be finished

    def shifted(self, dx: float, dy: float) -> Course:
        def p(v: tuple[float, float]) -> tuple[float, float]:
            return (v[0] + dx, v[1] + dy)

        return Course(
            self.id,
            self.name,
            tuple(p(c) for c in self.checkpoints),
            tuple((a + dx, b + dy, c + dx, d + dy) for a, b, c, d in self.sand),
            tuple(p(c) for c in self.pads),
            p(self.supply) if self.supply else None,
            self.gate_radius_m,
            self.laps,
            self.limit_s,
            p(self.start_point) if self.start_point else None,
            tuple(p(c) for c in self.line),
            self.ground,
            self.style,
            self.drain_scale,
        )

    @property
    def start(self) -> tuple[float, float]:
        return self.start_point or self.checkpoints[-1]

    @property
    def path(self) -> tuple[tuple[float, float], ...]:
        return self.line or (self.start, *self.checkpoints)

    def in_sand(self, x: float, y: float) -> bool:
        return any(a <= x <= c and b <= y <= d for a, b, c, d in self.sand)

    def lap_length_m(self) -> float:
        pts = self.path
        return sum(math.dist(a, b) for a, b in zip(pts, pts[1:], strict=False))

    def document(self) -> JsonDict:
        return {
            "id": self.id,
            "name": self.name,
            "checkpoints": [list(c) for c in self.checkpoints],
            "sand": [list(s) for s in self.sand],
            "pads": [list(c) for c in self.pads],
            "supply": list(self.supply) if self.supply else None,
            "gate_radius_m": self.gate_radius_m,
            "laps": self.laps,
            "lap_length_m": round(self.lap_length_m(), 2),
            "start": list(self.start),
            "line": [list(c) for c in self.path],
            "ground": self.ground,
            "style": self.style,
        }


COURSES = {
    "crater_loop": Course(
        "crater_loop",
        "Crater Loop",
        ((9.0, 0.0), (14.0, 5.0), (9.0, 11.0), (1.0, 11.0), (-4.0, 5.5), (0.0, 0.0)),
        sand=((10.5, 1.5, 16.0, 8.5),),
        pads=((5.0, 0.0), (5.0, 11.0)),
        supply=(-3.5, 8.5),
    ),
    "dune_sprint": Course(
        "dune_sprint",
        "Dune Sprint",
        ((10.0, 0.0), (10.0, 6.0), (0.0, 6.0), (0.0, 0.0)),
        sand=((3.0, 4.0, 7.0, 8.0),),
        pads=((5.0, 0.0),),
        laps=3,
    ),
    # Routed on the Gale heightfield: 4 m baseline slope under 10 degrees, with 3 m clearance.
    # Flags sit on the path. The loop rounds the outcrop knoll north-east of the start and
    # climbs about 7 m.
    "gale_links": Course(
        "gale_links",
        "Gale Links",
        (
            (41.0, -6.0),
            (78.0, 6.0),
            (77.0, 42.0),
            (62.0, 67.0),
            (33.0, 74.0),
            (9.0, 51.0),
            (0.0, 0.0),
        ),
        pads=((59.5, 0.0), (9.0, 44.0)),
        supply=(77.0, 42.0),
        laps=1,
        limit_s=1500.0,
        drain_scale=0.7,
        line=(
            (0.0, 0.0),
            (22.0, 8.0),
            (24.0, 8.0),
            (26.0, 6.0),
            (28.0, 4.0),
            (30.0, 2.0),
            (41.0, -6.0),
            (78.0, 6.0),
            (77.0, 42.0),
            (81.0, 58.0),
            (81.0, 64.0),
            (79.0, 66.0),
            (62.0, 67.0),
            (50.0, 61.0),
            (48.0, 61.0),
            (46.0, 61.0),
            (44.0, 63.0),
            (42.0, 65.0),
            (40.0, 67.0),
            (38.0, 69.0),
            (36.0, 71.0),
            (33.0, 74.0),
            (25.0, 70.0),
            (23.0, 68.0),
            (21.0, 66.0),
            (19.0, 64.0),
            (17.0, 64.0),
            (13.0, 62.0),
            (11.0, 60.0),
            (9.0, 58.0),
            (9.0, 51.0),
            (9.0, 37.0),
            (3.0, 24.0),
            (0.0, 0.0),
        ),
        ground="gale",
        style="flags",
    ),
    "gale_sprint": Course(
        "gale_sprint",
        "Gale Sprint",
        ((41.0, -6.0), (78.0, 6.0), (77.0, 42.0)),
        pads=((59.5, 0.0),),
        laps=1,
        limit_s=900.0,
        drain_scale=0.7,
        start_point=(0.0, 0.0),
        line=(
            (0.0, 0.0),
            (22.0, 8.0),
            (24.0, 8.0),
            (26.0, 6.0),
            (28.0, 4.0),
            (30.0, 2.0),
            (41.0, -6.0),
            (78.0, 6.0),
            (77.0, 42.0),
        ),
        ground="gale",
        style="flags",
    ),
}


def color_of(paint: str) -> list[float]:
    return list(COLORS.get(paint, COLORS["ivory"]))


def _draw(seed: int, *parts: object) -> float:
    text = ":".join(str(p) for p in (seed, *parts))
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) / 2**32


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def fmt_time(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


# ---------------------------------------------------------------------------- racers


@dataclass
class Racer:
    id: str
    name: str
    kind: str  # you | npc | ghost
    design: JsonDict
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    speed: float = 0.0
    lap: int = 0
    next_cp: int = 0
    finished_s: float | None = None
    lap_times: list[float] = field(default_factory=list)
    lap_start_s: float = 0.0
    charge: float = 100.0
    boosts: int = 2
    boost_until: float = -1.0
    boost_held: bool = False
    pad_ready: dict[int, float] = field(default_factory=dict)
    resets: int = 0
    penalty_s: float = 0.0
    message: str = ""
    message_until: float = 0.0
    samples: list[list[float]] = field(default_factory=list)
    ghost_total: float | None = None
    path_i: int = 1

    @property
    def color(self) -> list[float]:
        return color_of(str(self.design.get("paint", "ivory")))


@dataclass(frozen=True)
class NpcProfile:
    name: str
    design: JsonDict
    pace: float  # share of the difficulty's pace
    line_m: float  # lateral offset of its racing line
    boost_charge: float  # boosts above this charge on straights


NPC_ROSTER = (
    NpcProfile("Dune Runner", garage("sand", "standard", "basic", "orange"), 1.0, 0.6, 40),
    NpcProfile("Long Haul", garage("allround", "endurance", "basic", "slate"), 1.02, -0.6, 30),
    NpcProfile("Scout-7", garage("allround", "standard", "scout", "gold"), 0.98, 0.0, 55),
    NpcProfile("Regolith", garage("sand", "endurance", "basic", "teal"), 1.03, -0.3, 35),
    NpcProfile("Kestrel", garage("allround", "standard", "basic", "cyan"), 0.97, 0.3, 50),
)


# ---------------------------------------------------------------------------- agents


@dataclass(frozen=True)
class RaceAction:
    linear_velocity_mps: float
    yaw_rate_radps: float
    boost: bool = False

    @staticmethod
    def parse(body: Any) -> RaceAction:
        if not isinstance(body, dict):
            raise ContractError("race action must be an object")
        v, w = body.get("linear_velocity_mps"), body.get("yaw_rate_radps")
        boost = body.get("boost", False)
        if (
            not isinstance(v, (int, float))
            or not isinstance(w, (int, float))
            or isinstance(v, bool)
            or isinstance(w, bool)
            or not math.isfinite(v)
            or not math.isfinite(w)
            or not isinstance(boost, bool)
        ):
            raise ContractError("race action needs finite linear_velocity_mps, yaw_rate_radps")
        return RaceAction(
            max(-MAX_SPEED_MPS, min(MAX_SPEED_MPS, float(v))),
            max(-MAX_YAW_RADPS, min(MAX_YAW_RADPS, float(w))),
            boost,
        )


STOP = RaceAction(0.0, 0.0)


class RaceAgent(Protocol):
    """An Advanced-mode driver. It sees only the public brief and observations."""

    name: str

    def reset(self, brief: JsonDict) -> None: ...

    def act(self, observation: JsonDict) -> RaceAction: ...


def steer(obs: JsonDict, target: Sequence[float], speed_share: float = 1.0) -> RaceAction:
    x, y = obs["position_m"][:2]
    heading = math.atan2(target[1] - y, target[0] - x)
    err = wrap(heading - obs["yaw_rad"])
    w = max(-MAX_YAW_RADPS, min(MAX_YAW_RADPS, 1.6 * err))
    v = MAX_SPEED_MPS * speed_share * max(0.15, math.cos(err)) if abs(err) < 1.4 else 0.05
    return RaceAction(v, w)


class PursuitAgent:
    """A classical pure-pursuit driver: always the next checkpoint, boost on long straights."""

    name = "pursuit"

    def reset(self, brief: JsonDict) -> None:
        self.brief = brief

    def act(self, observation: JsonDict) -> RaceAction:
        ahead: list[list[float]] = observation.get("path_ahead") or observation["next_checkpoints"]
        nxt = ahead[0]
        a = steer(observation, nxt)
        far = math.dist(observation["position_m"][:2], nxt) > 4.5
        straight = abs(a.yaw_rate_radps) < 0.1
        return RaceAction(a.linear_velocity_mps, a.yaw_rate_radps, far and straight)


# Code-as-policy: a plan is data over typed skills, never code (ADR 0008).
RACE_SKILLS: dict[str, dict[str, tuple[float, float]]] = {
    "follow_checkpoints": {"lookahead_m": (0.0, 3.0), "speed_share": (0.3, 1.0)},
    "boost_on_straights": {"min_distance_m": (2.0, 15.0), "min_charge": (0.0, 100.0)},
    "detour_sand": {"margin_m": (0.0, 3.0)},
    "visit_supply": {"below_charge": (0.0, 100.0)},
}


def validate_plan(plan: Any) -> list[JsonDict]:
    """Accept only known skills with bounded numeric arguments."""
    if not isinstance(plan, list) or not 1 <= len(plan) <= 8:
        raise ContractError("a race plan is a list of 1 to 8 skill calls")
    out = []
    for call in plan:
        if not isinstance(call, dict) or set(call) - {"skill", "args", "reason"}:
            raise ContractError("a skill call has only skill, args and reason")
        name, args = call.get("skill"), call.get("args", {})
        if name not in RACE_SKILLS or not isinstance(args, dict):
            raise ContractError(f"unknown race skill: {name!r}")
        spec = RACE_SKILLS[name]
        clean = {}
        for key, value in args.items():
            if key not in spec or isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ContractError(f"invalid argument {key!r} for {name}")
            lo, hi = spec[key]
            if not math.isfinite(value) or not lo <= value <= hi:
                raise ContractError(f"{name}.{key} must be within {lo} and {hi}")
            clean[key] = float(value)
        out.append({"skill": name, "args": clean, "reason": str(call.get("reason", ""))[:200]})
    if not any(c["skill"] == "follow_checkpoints" for c in out):
        raise ContractError("a race plan must include follow_checkpoints")
    return out


class PlanSource(Protocol):
    """Where a CaP plan comes from: a rule-based mock here, or a language model you connect."""

    def plan(self, brief: JsonDict, report: JsonDict | None) -> Any: ...


class MockPlanner:
    """Fixed rules standing in for a language model. No model is called."""

    def plan(self, brief: JsonDict, report: JsonDict | None) -> Any:
        sand_tires = brief["garage"]["tires"] == "sand"
        plan: list[JsonDict] = [
            {"skill": "follow_checkpoints", "args": {"lookahead_m": 1.5, "speed_share": 1.0}},
            {"skill": "boost_on_straights", "args": {"min_distance_m": 4.5, "min_charge": 25}},
        ]
        if not sand_tires:
            plan.append({"skill": "detour_sand", "args": {"margin_m": 1.0}})
        if report and report.get("charge", 100) < 45:
            plan.append({"skill": "visit_supply", "args": {"below_charge": 45}})
        return plan


class CapAgent:
    """Executes a validated skill plan; asks its plan source again after every lap."""

    name = "cap"

    def __init__(self, source: PlanSource | None = None):
        self.source = source or MockPlanner()

    def reset(self, brief: JsonDict) -> None:
        self.brief = brief
        self.lap = 0
        self.plan = validate_plan(self.source.plan(brief, None))
        self.detour: tuple[float, float] | None = None

    def _skill(self, name: str) -> JsonDict | None:
        return next((c["args"] for c in self.plan if c["skill"] == name), None)

    def act(self, obs: JsonDict) -> RaceAction:
        if obs["lap"] != self.lap:
            self.lap = obs["lap"]
            report = {"lap": obs["lap"], "charge": obs["charge"], "position": obs["position"]}
            # Keep the last valid plan; a bad plan never reaches the rover
            with contextlib.suppress(ContractError):
                self.plan = validate_plan(self.source.plan(self.brief, report))
        follow = self._skill("follow_checkpoints") or {}
        ahead: list[list[float]] = obs.get("path_ahead") or obs["next_checkpoints"]
        target = list(ahead[0])
        p = obs["position_m"][:2]
        supply = self._skill("visit_supply")
        if supply and self.brief["course"]["supply"] and obs["charge"] < supply["below_charge"]:
            target = self.brief["course"]["supply"]
        sand = self._skill("detour_sand")
        if sand is not None:
            target = self._around_sand(p, target, sand.get("margin_m", 1.0))
        look = follow.get("lookahead_m", 1.5)
        if look and len(ahead) > 1 and math.dist(p, target) < look:
            target = list(ahead[1])
        a = steer(obs, target, follow.get("speed_share", 1.0))
        boost = self._skill("boost_on_straights")
        go = bool(
            boost
            and math.dist(p, target) > boost.get("min_distance_m", 4.5)
            and abs(a.yaw_rate_radps) < 0.1
            and obs["charge"] >= boost.get("min_charge", 25)
            and not obs["in_sand"]
        )
        return RaceAction(a.linear_velocity_mps, a.yaw_rate_radps, go)

    def _around_sand(self, p: Sequence[float], target: list[float], margin: float) -> list[float]:
        """Detour round a sand patch only when the detour is expected to be quicker."""
        slow = 1 / max(0.1, self.brief["stats"]["sand_scale"])
        for a, b, c, d in self.brief["course"]["sand"]:
            if a <= p[0] <= c and b <= p[1] <= d:
                continue
            fractions = [i / 20 for i in range(1, 20)]
            inside = sum(
                a <= p[0] + (target[0] - p[0]) * f <= c and b <= p[1] + (target[1] - p[1]) * f <= d
                for f in fractions
            )
            if not inside:
                continue
            direct = math.dist(p, target)
            through = direct + direct * inside / 20 * (slow - 1)
            corners = [
                (a - margin, b - margin),
                (a - margin, d + margin),
                (c + margin, b - margin),
                (c + margin, d + margin),
            ]
            best = min(corners, key=lambda q: math.dist(p, q) + math.dist(q, target))
            if math.dist(p, best) + math.dist(best, target) + 1.0 < through:
                return list(best)
        return target


BUILTIN_AGENTS: dict[str, Callable[[], RaceAgent]] = {"pursuit": PursuitAgent, "cap": CapAgent}


# ---------------------------------------------------------------------------- the race


class Race:
    """Rules for one race. Unreal (or the headless model) moves the player; Python judges."""

    def __init__(
        self,
        design: JsonDict,
        course: Course,
        *,
        player: str = "You",
        laps: int | None = None,
        npcs: int = 3,
        difficulty: str = "standard",
        seed: int = 1,
        ghosts: Sequence[JsonDict] = (),
        controller: str = "human",
        backend: str = "unreal",
    ):
        if difficulty not in DIFFICULTIES or type(seed) is not int or seed < 0:
            raise ContractError("invalid race difficulty or seed")
        if not 0 <= npcs <= len(NPC_ROSTER) or len(ghosts) > 3:
            raise ContractError(f"use 0 to {len(NPC_ROSTER)} NPCs and at most 3 ghosts")
        self.course = course
        self.laps = laps or course.laps
        if not 1 <= self.laps <= 9:
            raise ContractError("laps must be 1 to 9")
        self.difficulty, self.seed = difficulty, seed
        self.controller, self.backend = controller, backend
        self.time_s = -COUNTDOWN_S  # race clock; negative during the countdown
        self.clock0: float | None = None
        self.outcome = "running"
        design = garage(design["tires"], design["battery"], design["sensor"], design["paint"])
        sx, sy = course.start
        aim = course.path[1] if len(course.path) > 1 else course.checkpoints[0]
        yaw0 = math.atan2(aim[1] - sy, aim[0] - sx)
        self.you = Racer("you", player[:24] or "You", "you", design, sx, sy, yaw0)
        self.racers = [self.you]
        grid = ((-2.5, 1.8), (-2.5, -1.8), (-5.0, 0.0), (-7.5, 1.8), (-7.5, -1.8))
        cos, sin = math.cos(yaw0), math.sin(yaw0)
        self.profiles: dict[str, NpcProfile] = {}
        for i in range(npcs):
            prof = NPC_ROSTER[i]
            gx, gy = grid[i]
            r = Racer(
                f"npc{i + 1}",
                prof.name,
                "npc",
                prof.design,
                sx + gx * cos - gy * sin,
                sy + gx * sin + gy * cos,
                yaw0,
            )
            self.racers.append(r)
            self.profiles[r.id] = prof
        for r in self.racers:
            r.charge = stats(r.design)["capacity"]
        self.ghosts = [GhostTrack(g, i) for i, g in enumerate(ghosts)]
        for g in self.ghosts:
            self.racers.append(g.racer)

    # -- shared rules ---------------------------------------------------------------

    def dust(self, t: float) -> bool:
        slot = int(t // 20)
        return (
            t >= 20
            and t % 20 >= 16
            and _draw(self.seed, "dust", slot) < DIFFICULTIES[self.difficulty][0]
        )

    def dust_warning(self, r: Racer) -> bool:
        t = self.time_s
        nxt = self.dust((int(t // 20) + 1) * 20 - 0.01) if t >= 0 else False
        return nxt and t % 20 >= 16 - stats(r.design)["warning_s"]

    def scale(self, r: Racer) -> float:
        if self.time_s < 0 or r.finished_s is not None or self.outcome != "running":
            return 0.0
        spec = stats(r.design)
        s = spec["cruise_scale"] * (spec["sand_scale"] if self.course.in_sand(r.x, r.y) else 1.0)
        s *= BOOST_SCALE if self.time_s < r.boost_until else 1.0
        s *= 0.75 if self.dust(self.time_s) else 1.0
        return 0.0 if r.charge <= 0 else min(1.5, s)

    def _say(self, r: Racer, text: str) -> None:
        r.message, r.message_until = text, self.time_s + 2.5

    def _rules(self, r: Racer, dt: float, boost: bool) -> None:
        """Charge, boost, pads, supply and checkpoints for any racer except ghosts."""
        t = self.time_s
        spec = stats(r.design)
        drain = (spec["idle_drain"] + abs(r.speed) * 0.35) * self.course.drain_scale
        r.charge = max(0.0, r.charge - dt * drain)
        if boost and not r.boost_held and r.boosts and r.charge >= 8 and t >= r.boost_until:
            r.boosts -= 1
            r.charge -= 8
            r.boost_until = t + BOOST_S
            self._say(r, "BOOST!")
        r.boost_held = boost
        for i, pad in enumerate(self.course.pads):
            if math.dist((r.x, r.y), pad) <= 1.2 and t >= r.pad_ready.get(i, 0.0):
                r.pad_ready[i] = t + PAD_COOLDOWN_S
                if r.boosts < MAX_BOOSTS:
                    r.boosts += 1
                    self._say(r, "Boost pad: +1 boost")
        if self.course.supply and math.dist((r.x, r.y), self.course.supply) <= 3.0:
            before = r.charge
            r.charge = min(spec["capacity"], r.charge + 15 * dt)
            if before < r.charge and t >= r.message_until:
                self._say(r, "Recharging")
        self._checkpoint(r)

    def _checkpoint(self, r: Racer) -> None:
        t = self.time_s
        cp = self.course.checkpoints[r.next_cp]
        if r.finished_s is None and math.dist((r.x, r.y), cp) <= self.course.gate_radius_m:
            r.next_cp += 1
            if r.next_cp == len(self.course.checkpoints):
                r.next_cp = 0
                r.lap += 1
                r.lap_times.append(t - r.lap_start_s)
                r.lap_start_s = t
                if r.lap >= self.laps:
                    r.finished_s = t + r.penalty_s if r.kind != "ghost" else r.ghost_total or t
                    self._say(r, "FINISH")
                else:
                    self._say(r, f"Lap {r.lap + 1}/{self.laps}  ({fmt_time(r.lap_times[-1])})")

    def progress(self, r: Racer) -> float:
        n = len(self.course.checkpoints)
        cps = (self.course.start if r.next_cp == 0 else self.course.checkpoints[r.next_cp - 1],)
        a, b = cps[0], self.course.checkpoints[r.next_cp]
        seg = max(0.1, math.dist(a, b))
        part = max(0.0, min(1.0, 1 - math.dist((r.x, r.y), b) / seg))
        done = r.lap * n + r.next_cp
        return done + (0.0 if r.finished_s is not None else part)

    def standings(self) -> list[Racer]:
        done = sorted(
            (r for r in self.racers if r.finished_s is not None), key=lambda r: r.finished_s or 0
        )
        rest = sorted(
            (r for r in self.racers if r.finished_s is None), key=lambda r: -self.progress(r)
        )
        return done + rest

    # -- NPC driver -----------------------------------------------------------------

    def _npc_action(self, r: Racer) -> RaceAction:
        """Follow the course path, a little to one side, with seeded wobble. Ignores the player."""
        prof = self.profiles[r.id]
        path = self.course.path
        while math.dist((r.x, r.y), path[r.path_i]) < 2.0:
            r.path_i += 1
            if r.path_i == len(path):
                r.path_i = 1  # loops start again after the start point
        a, b = path[r.path_i - 1], path[r.path_i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy) or 1.0
        side = prof.line_m * (0.5 if self.course.style == "flags" else 1.0)
        target = (b[0] - dy / norm * side, b[1] + dx / norm * side)
        obs = {"position_m": [r.x, r.y], "yaw_rad": r.yaw}
        wobble = 0.12 * (_draw(self.seed, r.id, int(self.time_s // 2)) - 0.5)
        act = steer(obs, target, DIFFICULTIES[self.difficulty][1] * prof.pace)
        far = math.dist((r.x, r.y), b) > 5
        boost = far and abs(act.yaw_rate_radps) < 0.1 and r.charge > prof.boost_charge
        return RaceAction(act.linear_velocity_mps, act.yaw_rate_radps + wobble, boost)

    def _move(self, r: Racer, act: RaceAction, dt: float) -> None:
        target = act.linear_velocity_mps * self.scale(r)
        step = ACCEL_MPS2 * dt
        r.speed += max(-step, min(step, target - r.speed))
        yaw_rate = act.yaw_rate_radps if self.scale(r) > 0 else 0.0
        r.yaw = wrap(r.yaw + yaw_rate * dt)
        r.x += r.speed * math.cos(r.yaw) * dt
        r.y += r.speed * math.sin(r.yaw) * dt

    # -- stepping -------------------------------------------------------------------

    def step(self, body: JsonDict, boost: bool | None = None) -> JsonDict:
        """One telemetry message for the player's rover, from Unreal or the headless model."""
        t_raw = float(body["time_s"])
        p = body["position_m"]
        if self.clock0 is None:
            self.clock0 = t_raw + COUNTDOWN_S
        t = t_raw - self.clock0
        speed = float(body.get("forward_mps", 0.0))
        resets = body.get("resets", 0)
        if (
            not isinstance(p, list)
            or len(p) != 3
            or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (*p, t, speed))
            or t < self.time_s - 1e-9
        ):
            raise ContractError("invalid race telemetry or decreasing clock")
        if type(resets) is not int or resets < self.you.resets:
            raise ContractError("invalid reset count")
        dt = max(0.0, t - self.time_s)
        self.time_s = t
        you = self.you
        you.x, you.y = float(p[0]), float(p[1])
        if isinstance(body.get("yaw_rad"), (int, float)) and math.isfinite(body["yaw_rad"]):
            you.yaw = float(body["yaw_rad"])
        you.speed = speed
        if resets > you.resets:
            you.penalty_s += 30 * (resets - you.resets)
            self._say(you, "Rescue: +30 s")
        you.resets = resets
        if self.outcome == "running" and t >= 0:
            if you.finished_s is None:
                want = bool(body.get("boost_requested", False)) if boost is None else boost
                self._rules(you, min(dt, 0.5), want)
            # Fixed sub-steps keep NPCs independent of the telemetry rate.
            remaining = min(dt, 1.0)
            while remaining > 1e-9:
                h = min(TICK_S, remaining)
                remaining -= h
                for r in self.racers:
                    if r.kind == "npc" and r.finished_s is None:
                        act = self._npc_action(r)
                        self._move(r, act, h)
                        self._rules(r, h, act.boost)
            for g in self.ghosts:
                g.update(t)
                self._checkpoint(g.racer)
            if you.finished_s is not None:
                self.outcome = "finished"
            elif t >= self.course.limit_s:
                self.outcome = "time_limit"
            elif you.charge <= 0 and you.speed <= 0.01:
                self.outcome = "battery_empty"
        due = not you.samples or t >= you.samples[-1][0] + 0.25
        final = (
            you.finished_s is not None
            and bool(you.samples)
            and you.samples[-1][0] < you.lap_start_s
        )
        if t >= 0 and (due or final):
            you.samples.append([round(t, 2), round(you.x, 3), round(you.y, 3), round(you.yaw, 3)])
        return self.state()

    def position_of(self, racer: Racer) -> int:
        return self.standings().index(racer) + 1

    def state(self) -> JsonDict:
        you, t = self.you, self.time_s
        order = self.standings()
        pos = order.index(you) + 1
        lead = order[0]
        rows = []
        for i, r in enumerate(order):
            if r.finished_s is not None:
                gap = (
                    fmt_time(r.finished_s)
                    if i == 0
                    else f"+{r.finished_s - (lead.finished_s or 0):.1f}s"
                )
            else:
                behind = self.progress(lead) - self.progress(r)
                gap = "" if i == 0 else f"-{behind:.1f} cp"
            rows.append(
                {
                    "pos": i + 1,
                    "name": r.name,
                    "kind": r.kind,
                    "gap": gap,
                    "lap": min(r.lap + 1, self.laps),
                    "color": r.color,
                    "is_you": r is you,
                }
            )
        if t < 0:
            banner = str(math.ceil(-t))
        elif t < 1.2:
            banner = "GO!"
        elif self.outcome == "finished":
            banner = f"FINISH  {ordinal(pos)}"
        elif self.outcome != "running":
            banner = self.outcome.replace("_", " ").upper()
        else:
            banner = ""
        targets = [] if self.outcome != "running" else [list(self.course.checkpoints[you.next_cp])]
        line = f"Lap {min(you.lap + 1, self.laps)}/{self.laps} | {ordinal(pos)} of {len(order)}"
        line += f" | {fmt_time(max(0.0, t))} | charge {you.charge:.0f} | boosts {you.boosts}"
        return {
            "scenario": "race",
            "time_s": max(0.0, t),
            "targets_reached": min(you.lap, self.laps),
            "targets_total": self.laps,
            "outcome": "success" if self.outcome == "finished" else self.outcome,
            "drive_scale": self.scale(you),
            "targets": targets,
            "rally_line": line,
            "result_time_s": you.finished_s if you.finished_s is not None else t + you.penalty_s,
            "position_m": [you.x, you.y, 0.0],
            "ruleset": RULESET,
            "model_version": MODEL_VERSION,
            "race": {
                "lap": min(you.lap + 1, self.laps),
                "laps": self.laps,
                "position": pos,
                "racers": len(order),
                "time": fmt_time(max(0.0, t)),
                "best_lap": fmt_time(min(you.lap_times)) if you.lap_times else "",
                "charge": round(you.charge / stats(you.design)["capacity"], 3),
                "boosts": you.boosts,
                "flag": you.next_cp + 1,
                "flags": len(self.course.checkpoints),
                "boosting": t < you.boost_until,
                "in_sand": self.course.in_sand(you.x, you.y),
                "dust": self.dust(t) if t >= 0 else False,
                "dust_warning": self.dust_warning(you),
                "banner": banner,
                "message": you.message if t < you.message_until else "",
                "controller": self.controller,
                "standings": rows,
                "opponents": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "kind": r.kind,
                        "position_m": [round(r.x, 3), round(r.y, 3), 0.0],
                        "yaw_rad": round(r.yaw, 4),
                        "color": r.color,
                        "pos": order.index(r) + 1,
                    }
                    for r in self.racers
                    if r is not you and (r.kind != "ghost" or r.samples)
                ],
            },
        }

    # -- agent view -----------------------------------------------------------------

    def brief(self) -> JsonDict:
        return {
            "protocol": AGENT_PROTOCOL,
            "ruleset": RULESET,
            "course": self.course.document(),
            "laps": self.laps,
            "garage": self.you.design,
            "stats": stats(self.you.design),
            "limits": {"max_speed_mps": MAX_SPEED_MPS, "max_yaw_rate_radps": MAX_YAW_RADPS},
            "tick_s": TICK_S,
            "boost": {"duration_s": BOOST_S, "scale": BOOST_SCALE, "cost": 8, "max": MAX_BOOSTS},
        }

    def observation(self) -> JsonDict:
        you = self.you
        cps = self.course.checkpoints
        nxt = [list(cps[(you.next_cp + k) % len(cps)]) for k in range(3)]
        others = [
            {
                "name": r.name,
                "kind": r.kind,
                "position_m": [round(r.x, 3), round(r.y, 3)],
                "lap": r.lap,
            }
            for r in self.racers
            if r is not you
        ]
        path = self.course.path
        while math.dist((you.x, you.y), path[you.path_i]) < 2.0:
            you.path_i += 1
            if you.path_i == len(path):
                you.path_i = len(path) - 1 if self.course.start_point else 1
                break
        ahead = [list(path[min(you.path_i + k, len(path) - 1)]) for k in range(3)]
        return {
            "time_s": round(self.time_s, 3),
            "started": self.time_s >= 0,
            "path_ahead": ahead,
            "position_m": [you.x, you.y],
            "yaw_rad": you.yaw,
            "speed_mps": you.speed,
            "lap": you.lap,
            "laps": self.laps,
            "next_checkpoints": nxt,
            "position": self.position_of(you),
            "charge": round(you.charge, 2),
            "boosts": you.boosts,
            "boosting": self.time_s < you.boost_until,
            "in_sand": self.course.in_sand(you.x, you.y),
            "dust": self.dust(self.time_s) if self.time_s >= 0 else False,
            "dust_warning": self.dust_warning(you),
            "opponents": others,
            "finished": you.finished_s is not None or self.outcome != "running",
        }

    # -- results --------------------------------------------------------------------

    def result(self) -> JsonDict:
        you = self.you
        return {
            "ruleset": RULESET,
            "model_version": MODEL_VERSION,
            "backend": self.backend,
            "controller": self.controller,
            "player": you.name,
            "course": self.course.id,
            "laps": self.laps,
            "difficulty": self.difficulty,
            "seed": self.seed,
            "design": you.design,
            "outcome": "success" if self.outcome == "finished" else self.outcome,
            "position": self.position_of(you),
            "racers": len(self.racers),
            "total_s": round(you.finished_s, 2) if you.finished_s is not None else None,
            "lap_times_s": [round(t, 2) for t in you.lap_times],
            "penalty_s": you.penalty_s,
            "standings": [
                {
                    "pos": i + 1,
                    "name": r.name,
                    "kind": r.kind,
                    "total_s": round(r.finished_s, 2) if r.finished_s is not None else None,
                }
                for i, r in enumerate(self.standings())
            ],
            "samples": you.samples[:4000],
        }


def ordinal(n: int) -> str:
    return f"{n}{'tsnrhtdd'[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10 :: 4]}"


class GhostTrack:
    """A previous run, replayed by race time. It never collides and never scores."""

    def __init__(self, entry: JsonDict, index: int):
        samples = entry.get("samples")
        if not isinstance(samples, list) or not 2 <= len(samples) <= 4000:
            raise ContractError("ghost needs 2 to 4000 samples")
        last = -1.0
        for s in samples:
            if (
                not isinstance(s, list)
                or len(s) != 4
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in s)
                or s[0] <= last
            ):
                raise ContractError("invalid ghost samples")
            last = s[0]
        self.samples = samples
        self.racer = Racer(
            f"ghost{index + 1}",
            f"{str(entry.get('player', 'Ghost'))[:18]} (ghost)",
            "ghost",
            garage(**{k: entry["design"][k] for k in ("tires", "battery", "sensor", "paint")}),
        )
        total = entry.get("total_s")
        self.racer.ghost_total = float(total) if isinstance(total, (int, float)) else None
        self.racer.x, self.racer.y, self.racer.yaw = samples[0][1:]
        self.i = 0

    def update(self, t: float) -> None:
        s, r = self.samples, self.racer
        while self.i + 1 < len(s) and s[self.i + 1][0] <= t:
            self.i += 1
        a = s[self.i]
        if self.i + 1 < len(s):
            b = s[self.i + 1]
            f = max(0.0, min(1.0, (t - a[0]) / (b[0] - a[0])))
            r.x, r.y = a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f
            r.yaw = a[3] + wrap(b[3] - a[3]) * f
        else:
            r.x, r.y, r.yaw = a[1], a[2], a[3]
            if r.ghost_total is not None and t >= r.ghost_total:
                r.finished_s = r.ghost_total  # its recording ends at its finish
        r.samples = s  # marks it visible


# ---------------------------------------------------------------------------- headless


def simulate(race: Race, agent: RaceAgent, max_s: float | None = None) -> JsonDict:
    """Drive the player with the race model instead of Unreal. Deterministic for one seed."""
    agent.reset(race.brief())
    t = 0.0
    limit = max_s if max_s is not None else race.course.limit_s + COUNTDOWN_S
    race.step({"time_s": 0.0, "position_m": [race.you.x, race.you.y, 0.0], "yaw_rad": race.you.yaw})
    while race.outcome == "running" and t < limit:
        act = agent.act(race.observation()) if race.time_s >= 0 else STOP
        race._move(race.you, act, TICK_S)
        t = round(t + TICK_S, 6)
        race.step(
            {
                "time_s": t,
                "position_m": [race.you.x, race.you.y, 0.0],
                "yaw_rad": race.you.yaw,
                "forward_mps": race.you.speed,
            },
            boost=act.boost,
        )
    return race.result()


# ---------------------------------------------------------------------------- leaderboard


def entry_hash(entry: JsonDict) -> str:
    body = {k: v for k, v in entry.items() if k != "entry_id"}
    return hashlib.sha256(dump_json(body).encode()).hexdigest()[:16]


def check_entry(entry: Any) -> JsonDict:
    """Data checks for a shared entry. This is not anti-cheat; anyone can edit a file."""
    if not isinstance(entry, dict):
        raise ContractError("leaderboard entry must be an object")
    need = {"ruleset", "backend", "controller", "player", "course", "laps", "design", "total_s"}
    if need - set(entry) or entry["ruleset"] != RULESET:
        raise ContractError("unsupported leaderboard entry")
    if entry["course"] not in COURSES or entry["backend"] not in ("unreal", "headless"):
        raise ContractError("unknown course or backend")
    total = entry["total_s"]
    if not isinstance(total, (int, float)) or not 1 <= total <= 3600:
        raise ContractError("entry needs a finished time")
    garage(**{k: entry["design"][k] for k in ("tires", "battery", "sensor", "paint")})
    if "samples" in entry:
        GhostTrack(entry, 0)
    clean = dict(entry)
    clean["player"] = str(entry["player"])[:24]
    clean["entry_id"] = entry_hash(clean)
    return clean


def board_key(entry: JsonDict) -> str:
    who = "agent" if str(entry["controller"]).startswith("agent") else "human"
    return f"{entry['course']}/{entry['laps']}lap/{entry['backend']}/{who}"


class Leaderboard:
    """A local JSON file. Share runs by exporting one entry and importing it on another machine."""

    def __init__(self, path: Path):
        self.path = path
        self.entries: list[JsonDict] = []
        if path.exists():
            if path.stat().st_size > 50_000_000:
                raise ContractError("leaderboard file too large")
            doc = load_json_file(path)
            if doc.get("ruleset") != RULESET or not isinstance(doc.get("entries"), list):
                raise ContractError("unsupported leaderboard file")
            self.entries = [check_entry(e) for e in doc["entries"]]

    def add(self, entry: JsonDict) -> tuple[JsonDict, int]:
        clean = check_entry(entry)
        if not any(e["entry_id"] == clean["entry_id"] for e in self.entries):
            self.entries.append(clean)
        self.save()
        ranked = self.ranking(board_key(clean))
        return clean, next(
            i for i, e in enumerate(ranked) if e["entry_id"] == clean["entry_id"]
        ) + 1

    def ranking(self, key: str) -> list[JsonDict]:
        return sorted((e for e in self.entries if board_key(e) == key), key=lambda e: e["total_s"])

    def boards(self) -> dict[str, list[JsonDict]]:
        return {k: self.ranking(k) for k in sorted({board_key(e) for e in self.entries})}

    def ghosts_for(self, course: str, laps: int, backend: str, n: int) -> list[JsonDict]:
        pool = [
            e
            for e in self.entries
            if e["course"] == course
            and e["laps"] == laps
            and e["backend"] == backend
            and e.get("samples")
        ]
        return sorted(pool, key=lambda e: e["total_s"])[:n]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"ruleset": RULESET, "entries": self.entries}
        self.path.write_text(dump_json(doc) + "\n", encoding="utf-8")


def summary(entries: Sequence[JsonDict], limit: int = 10) -> list[JsonDict]:
    """The leaderboard without trajectories, for pages and terminals."""
    return [
        {
            "rank": i + 1,
            "player": e["player"],
            "total": fmt_time(e["total_s"]),
            "total_s": e["total_s"],
            "controller": e["controller"],
            "design": e["design"],
            "position": e.get("position"),
            "entry_id": e["entry_id"],
        }
        for i, e in enumerate(entries[:limit])
    ]


__all__ = ["COURSES", "PAINTS", "Race", "Leaderboard", "simulate", "BUILTIN_AGENTS"]
