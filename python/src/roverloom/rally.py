"""Experimental real-time rally rules, separate from scored simulator benchmarks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from roverloom.contract import ContractError, JsonDict, dump_json, load_json_file, repo_root

MODEL_VERSION = "rally-drive-0.1"
RULESET = "rally-0.1"
PAINTS = {
    "ivory": "0.8,0.76,0.62",
    "cyan": "0.12,0.65,0.75",
    "orange": "0.9,0.3,0.08",
    "slate": "0.32,0.36,0.4",
    "gold": "0.85,0.62,0.18",
    "teal": "0.1,0.45,0.42",
}
DIFFICULTIES = {"easy": 0.0, "standard": 0.2, "hard": 0.4}
GATES = (((5.0, -3.0), (5.0, 7.0)), ((14.0, 0.0),), ((22.0, 0.0),), ((0.0, 0.0),))
LABELS = (
    "Choose sand shortcut or firm detour",
    "Stop at supply for 2 seconds",
    "Stop to collect sample",
    "Return to start",
)


def garage(
    tires: str = "allround", battery: str = "standard", sensor: str = "basic", paint: str = "ivory"
) -> JsonDict:
    choices = {"tires": tires, "battery": battery, "sensor": sensor, "paint": paint}
    allowed = {
        "tires": ("allround", "sand"),
        "battery": ("standard", "endurance"),
        "sensor": ("basic", "scout"),
        "paint": tuple(PAINTS),
    }
    for key, value in choices.items():
        if value not in allowed[key]:
            raise ContractError(f"invalid rally {key}: {value}")
    return {"ruleset": RULESET, **choices}


def load_garage(path: Path | None) -> JsonDict:
    if path is None:
        return garage()
    value = load_json_file(path)
    if (
        set(value) != {"ruleset", "tires", "battery", "sensor", "paint"}
        or value["ruleset"] != RULESET
    ):
        raise ContractError("unsupported rally garage document")
    return garage(value["tires"], value["battery"], value["sensor"], value["paint"])


def design_hash(design: JsonDict) -> str:
    return hashlib.sha256(dump_json(design).encode()).hexdigest()


def stats(design: JsonDict) -> JsonDict:
    # Game balance values, not real battery capacity, mass, sensors, or terramechanics.
    return {
        "capacity": 120.0 if design["battery"] == "endurance" else 100.0,
        "cruise_scale": (0.9 if design["tires"] == "sand" else 1.0)
        * (0.9 if design["battery"] == "endurance" else 1.0),
        "sand_scale": 0.95 if design["tires"] == "sand" else 0.55,
        "warning_s": 8.0 if design["sensor"] == "scout" else 4.0,
        "idle_drain": 0.12 if design["sensor"] == "scout" else 0.08,
    }


@dataclass
class Rally:
    design: JsonDict
    difficulty: str = "easy"
    seed: int = 1
    time_s: float = 0.0
    reached: int = 0
    charge: float = field(init=False)
    boosts: int = 2
    boost_until: float = -1.0
    boost_held: bool = False
    dwell: float = 0.0
    resets: int = 0
    penalty: float = 0.0
    outcome: str = "running"
    samples: list[JsonDict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.design = garage(
            self.design["tires"],
            self.design["battery"],
            self.design["sensor"],
            self.design["paint"],
        )
        if self.difficulty not in DIFFICULTIES or type(self.seed) is not int or self.seed < 0:
            raise ContractError("invalid rally difficulty or seed")
        self.charge = stats(self.design)["capacity"]

    def weather(self, t: float) -> bool:
        # Global time slot + seed, independent of agent-specific RNG consumption.
        slot = int(t // 20)
        draw = (
            int(hashlib.sha256(f"{self.seed}:weather:{slot}".encode()).hexdigest()[:8], 16) / 2**32
        )
        return t >= 20 and t % 20 >= 16 and draw < DIFFICULTIES[self.difficulty]

    def step(self, body: JsonDict) -> JsonDict:
        t = float(body["time_s"])
        p = tuple(float(v) for v in body["position_m"])
        speed = float(body.get("forward_mps", 0.0))
        resets = body.get("resets", 0)
        if len(p) != 3 or not all(math.isfinite(v) for v in (*p, t, speed)) or t < self.time_s:
            raise ContractError("invalid rally telemetry or decreasing clock")
        if type(resets) is not int or resets < self.resets:
            raise ContractError("invalid reset count")
        dt = t - self.time_s
        if self.outcome != "running":
            return self.state(p)
        self.time_s = t
        spec = stats(self.design)
        self.penalty += 60 * (resets - self.resets)
        self.resets = resets
        self.charge = max(0.0, self.charge - dt * (spec["idle_drain"] + abs(speed) * 0.5))
        boost = bool(body.get("boost_requested", False))
        if (
            boost
            and not self.boost_held
            and self.boosts
            and self.charge >= 8
            and t >= self.boost_until
        ):
            self.boosts -= 1
            self.charge -= 8
            self.boost_until = t + 3
        self.boost_held = boost
        if t >= 240:
            self.outcome = "time_limit"
        elif self.charge <= 0:
            self.outcome = "battery_empty"
        else:
            near = any(math.dist(p[:2], gate) <= 2 for gate in GATES[self.reached])
            if self.reached in (1, 2):
                self.dwell = self.dwell + min(dt, 0.5) if near and abs(speed) <= 0.05 else 0.0
                near = near and self.dwell >= (2.0 if self.reached == 1 else 1.0)
            if near:
                if self.reached == 1:
                    self.charge = min(spec["capacity"], self.charge + 30)
                    self.boosts = min(2, self.boosts + 1)
                self.reached += 1
                self.dwell = 0.0
                if self.reached == len(GATES):
                    self.outcome = "success"
        state = self.state(p)
        if not self.samples or t > self.samples[-1]["time_s"]:
            self.samples.append({"time_s": t, "position_m": list(p)})
        return state

    def state(self, p: tuple[float, ...]) -> JsonDict:
        spec = stats(self.design)
        sand = 1 <= p[0] <= 9 and -7 <= p[1] <= -1
        scale = spec["cruise_scale"] * (spec["sand_scale"] if sand else 1.0)
        scale *= 1.5 if self.time_s < self.boost_until else 1.0
        scale *= 0.75 if self.weather(self.time_s) else 1.0
        scale = scale if self.outcome == "running" else 0.0
        targets = [] if self.outcome != "running" else [list(g) for g in GATES[self.reached]]
        next_storm = self.weather((int(self.time_s // 20) + 1) * 20 - 0.01)
        warning = next_storm and self.time_s % 20 >= 16 - spec["warning_s"]
        label = LABELS[self.reached] if self.reached < len(GATES) else "Finished"
        return {
            "scenario": "rally",
            "time_s": self.time_s,
            "targets_reached": self.reached,
            "targets_total": 4,
            "outcome": self.outcome,
            "drive_scale": scale,
            "targets": targets,
            "rally_line": f"{label} | charge {self.charge:.0f} | boosts {self.boosts} (SPACE) "
            f"| penalty {self.penalty:.0f}s" + (" | DUST WARNING" if warning else ""),
            "result_time_s": self.time_s + self.penalty,
            "position_m": list(p),
            "ruleset": RULESET,
            "model_version": MODEL_VERSION,
            "design_hash": design_hash(self.design),
        }

    def ghost_document(self) -> JsonDict:
        return {
            "ruleset": RULESET,
            "difficulty": self.difficulty,
            "seed": self.seed,
            "design": self.design,
            "samples": self.samples,
        }


class Ghost:
    def __init__(self, path: Path, difficulty: str, seed: int):
        if path.stat().st_size > 5_000_000:
            raise ContractError("ghost file too large")
        doc = load_json_file(path)
        if (doc.get("ruleset"), doc.get("difficulty"), doc.get("seed")) != (
            RULESET,
            difficulty,
            seed,
        ):
            raise ContractError("ghost ruleset, difficulty and seed must match")
        self.samples = doc.get("samples", [])
        if not isinstance(self.samples, list) or not 1 <= len(self.samples) <= 10000:
            raise ContractError("invalid ghost samples")
        last = -1.0
        for sample in self.samples:
            if not isinstance(sample, dict):
                raise ContractError("invalid ghost sample")
            t, p = sample.get("time_s"), sample.get("position_m")
            if (
                not isinstance(t, (int, float))
                or not math.isfinite(t)
                or t <= last
                or not isinstance(p, list)
                or len(p) != 3
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in p)
            ):
                raise ContractError("invalid ghost trajectory")
            last = t
        self.index = 0

    def at(self, t: float) -> list[float] | None:
        if t < self.samples[0]["time_s"] or t > self.samples[-1]["time_s"]:
            return None
        while self.index + 1 < len(self.samples) and self.samples[self.index + 1]["time_s"] <= t:
            self.index += 1
        a = self.samples[self.index]
        if self.index + 1 == len(self.samples):
            return list(a["position_m"])
        b = self.samples[self.index + 1]
        f = (t - a["time_s"]) / (b["time_s"] - a["time_s"])
        return [x + (y - x) * f for x, y in zip(a["position_m"], b["position_m"], strict=True)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tires", choices=("allround", "sand"), default="allround")
    parser.add_argument("--battery", choices=("standard", "endurance"), default="standard")
    parser.add_argument("--sensor", choices=("basic", "scout"), default="basic")
    parser.add_argument("--paint", choices=tuple(PAINTS), default="ivory")
    parser.add_argument("--out", type=Path, default=repo_root() / "runs" / "garage.json")
    parser.add_argument("--ui", action="store_true", help="write an offline garage page instead")
    args = parser.parse_args()
    if args.ui:
        page = args.out.with_suffix(".html")
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            (Path(__file__).parent / "preview" / "garage.html").read_text(), encoding="utf-8"
        )
        print(f"Open {page} in a browser")
        return
    design = garage(args.tires, args.battery, args.sensor, args.paint)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(dump_json(design) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"file": str(args.out), "hash": design_hash(design), "stats": stats(design)}, indent=2
        )
    )


if __name__ == "__main__":
    main()
