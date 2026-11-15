"""Where improved D's stalls come from: geometry measures, geometry variants, and their summary.

    python -m contact_solver.geometry variants --states <states.txt> --out <dir>
    python -m contact_solver.geometry summary --states <states.txt> --stalls <list> --out <dir>

Run from scripts/. `variants` writes one rewritten states file per variant. The C++ `geom` tool
then solves each, and `summary` reads its CSVs and applies the registered rules. Research only;
nothing here changes a solver, criterion, or record.
Plan: docs/results/unreal-wheel-model/stall-geometry.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any

Vec = list[float]

HEADER = 33  # numbers after "window index", before the wheels
# Per wheel: hit comp comp_rate point(3) normal(3) forward(3) lateral(3) mode target spin engine(4)
PER_WHEEL = 22
WHEELS = 6
PAIRS = ((0, 3), (1, 4), (2, 5))
VARIANTS = ("V0", "V1", "V2", "V3", "V4", "V6")
SEED = 20261107
TARGET = 1e-8


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec, b: Vec) -> Vec:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def sub(a: Vec, b: Vec) -> Vec:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def scale(a: Vec, s: float) -> Vec:
    return [a[0] * s, a[1] * s, a[2] * s]


def norm(a: Vec) -> float:
    return math.sqrt(dot(a, a))


def unit(a: Vec) -> Vec:
    return scale(a, 1.0 / norm(a))


def angle(a: Vec, b: Vec) -> float:
    """Angle between two directions, in degrees, robust near zero."""
    return math.degrees(math.atan2(norm(cross(a, b)), dot(a, b)))


def rotate(v: Vec, axis: Vec, theta: float) -> Vec:
    """Rodrigues rotation of v about a unit axis."""
    c, s = math.cos(theta), math.sin(theta)
    k = cross(axis, v)
    d = dot(axis, v) * (1 - c)
    return [v[i] * c + k[i] * s + axis[i] * d for i in range(3)]


class State:
    """One line of states.txt, with its wheel geometry as vectors."""

    def __init__(self, line: str) -> None:
        tokens = line.split()
        self.window, self.index = tokens[0], int(tokens[1])
        self.numbers = [float(t) for t in tokens[2:]]
        if len(self.numbers) != HEADER + WHEELS * PER_WHEEL:
            raise ValueError(f"unexpected state length {len(self.numbers)}")

    def _at(self, wheel: int, offset: int) -> int:
        return HEADER + wheel * PER_WHEEL + offset

    def hit(self, w: int) -> bool:
        return self.numbers[self._at(w, 0)] != 0

    def vec(self, w: int, field: str) -> Vec:
        start = self._at(w, {"point": 3, "normal": 6, "forward": 9, "lateral": 12}[field])
        return self.numbers[start : start + 3]

    def set_vec(self, w: int, field: str, value: Vec) -> None:
        start = self._at(w, {"point": 3, "normal": 6, "forward": 9, "lateral": 12}[field])
        self.numbers[start : start + 3] = value

    def normal_force(self, w: int) -> float:
        spring, damper = self.numbers[3], self.numbers[4]
        comp, rate = self.numbers[self._at(w, 1)], self.numbers[self._at(w, 2)]
        return max(0.0, spring * comp + damper * rate) if self.hit(w) else 0.0

    @property
    def com(self) -> Vec:
        return self.numbers[18:21]

    def contacts(self) -> list[int]:
        return [w for w in range(WHEELS) if self.hit(w)]

    def line(self) -> str:
        return f"{self.window} {self.index} " + " ".join(repr(v) for v in self.numbers)

    def copy(self) -> State:
        return State(self.line())


def mean_normal(s: State) -> Vec:
    return unit([sum(s.vec(w, "normal")[k] for w in s.contacts()) for k in range(3)])


def centroid(s: State) -> Vec:
    c = s.contacts()
    return [sum(s.vec(w, "point")[k] for w in c) / len(c) for k in range(3)]


def axes(s: State) -> tuple[Vec, Vec, Vec]:
    """Body axes estimated from the inputs: x along the mean forward, z along the mean normal."""
    z = mean_normal(s)
    f = [sum(s.vec(w, "forward")[k] for w in s.contacts()) for k in range(3)]
    x = unit(sub(f, scale(z, dot(f, z))))
    return x, cross(z, x), z


def measures(s: State) -> dict[str, float]:
    """M1 to M6 of the registered plan. NaN where too few wheels are in contact."""
    c = s.contacts()
    nan = float("nan")
    if len(c) < 3:
        return {k: nan for k in ("M1", "M2", "M3", "M4", "M5_angle", "M5_dx", "M6")}
    n, p0 = mean_normal(s), centroid(s)
    x, y, z = axes(s)
    m3 = 0.0
    for w in c:
        f, lat, nw = s.vec(w, "forward"), s.vec(w, "lateral"), s.vec(w, "normal")
        m3 = max(m3, abs(dot(f, nw)), abs(dot(lat, nw)), abs(dot(f, lat)))
        m3 = max(m3, abs(norm(f) - 1), abs(norm(lat) - 1), abs(norm(nw) - 1))
    m4, m6 = 0.0, 0.0
    loads = [s.normal_force(w) for w in c]
    mean_load = sum(loads) / len(loads)
    for a, b in PAIRS:
        if a in c and b in c:
            ra, rb = sub(s.vec(a, "point"), s.com), sub(s.vec(b, "point"), s.com)
            m4 = max(
                m4,
                abs(dot(ra, x) - dot(rb, x)),
                abs(abs(dot(ra, y)) - abs(dot(rb, y))),
                abs(dot(ra, z) - dot(rb, z)),
            )
            m6 = max(m6, abs(s.normal_force(a) - s.normal_force(b)) / mean_load)
    m5_angle, m5_dx = nan, nan
    if 1 in c and 4 in c:
        m5_angle = angle(s.vec(1, "lateral"), s.vec(4, "lateral"))
        r1, r4 = sub(s.vec(1, "point"), s.com), sub(s.vec(4, "point"), s.com)
        m5_dx = abs(dot(r1, x) - dot(r4, x))
    return {
        "M1": max(angle(s.vec(w, "normal"), n) for w in c),
        "M2": max(abs(dot(sub(s.vec(w, "point"), p0), n)) for w in c),
        "M3": m3,
        "M4": m4,
        "M5_angle": m5_angle,
        "M5_dx": m5_dx,
        "M6": m6,
    }


def wheel_order(states: list[State]) -> dict[str, Any]:
    """Check the assumed order: 0-2 on one side, 3-5 on the other, front to back, 1 and 4 middle."""
    sides_ok, middle_ok, front_ok, checked = 0, 0, 0, 0
    for s in states:
        if len(s.contacts()) < WHEELS:
            continue
        x, y, _ = axes(s)
        rx = [dot(sub(s.vec(w, "point"), s.com), x) for w in range(WHEELS)]
        ry = [dot(sub(s.vec(w, "point"), s.com), y) for w in range(WHEELS)]
        checked += 1
        left, right = (
            {math.copysign(1, ry[w]) for w in (0, 1, 2)},
            {math.copysign(1, ry[w]) for w in (3, 4, 5)},
        )
        sides_ok += len(left) == 1 and len(right) == 1 and left != right
        middle_ok += max(abs(rx[1]), abs(rx[4])) < min(abs(rx[w]) for w in (0, 2, 3, 5))
        front_ok += rx[0] > rx[2] and rx[3] > rx[5]
    return {"checked": checked, "sides": sides_ok, "middle": middle_ok, "front_to_back": front_ok}


def frames_against(s: State, w: int, n: Vec) -> None:
    """Make the wheel's forward and lateral orthonormal against n, keeping the forward heading."""
    f, lat = s.vec(w, "forward"), s.vec(w, "lateral")
    f2 = unit(sub(f, scale(n, dot(f, n))))
    l2 = sub(lat, scale(n, dot(lat, n)))
    l2 = unit(sub(l2, scale(f2, dot(l2, f2))))
    s.set_vec(w, "forward", f2)
    s.set_vec(w, "lateral", l2)


def variant(s: State, name: str, rng: random.Random) -> State:
    out = s.copy()
    c = s.contacts()
    if len(c) < 3:
        return out
    n, p0 = mean_normal(s), centroid(s)
    if name in ("V1", "V4"):
        for w in c:
            out.set_vec(w, "normal", n)
    if name in ("V3", "V4"):
        for w in c:
            p = s.vec(w, "point")
            out.set_vec(w, "point", sub(p, scale(n, dot(sub(p, p0), n))))
    if name == "V2":
        for w in c:
            frames_against(out, w, s.vec(w, "normal"))
    if name == "V4":
        for w in c:
            frames_against(out, w, n)
    if name == "V6":
        ideal = variant(s, "V4", rng)
        for w in c:
            theta = math.radians(
                max(angle(s.vec(w, k), ideal.vec(w, k)) for k in ("normal", "forward", "lateral"))
            )
            step = norm(sub(ideal.vec(w, "point"), s.vec(w, "point")))
            axis = unit([rng.gauss(0, 1) for _ in range(3)])
            for k in ("normal", "forward", "lateral"):
                out.set_vec(w, k, rotate(s.vec(w, k), axis, theta))
            move = unit([rng.gauss(0, 1) for _ in range(3)])
            out.set_vec(w, "point", [s.vec(w, "point")[i] + step * move[i] for i in range(3)])
    return out


def align_pairs(s: State, below: float = math.inf) -> State:
    """Exploratory, not registered: move each pair's second point along x to match the first."""
    out = s.copy()
    if len(s.contacts()) < 3:
        return out
    x, _, _ = axes(s)
    for a, b in PAIRS:
        if s.hit(a) and s.hit(b):
            pa, pb = s.vec(a, "point"), s.vec(b, "point")
            shift = dot(sub(pa, s.com), x) - dot(sub(pb, s.com), x)
            if abs(shift) >= below:
                continue
            out.set_vec(b, "point", [pb[i] + shift * x[i] for i in range(3)])
    return out


def explore(states: list[State], out: Path) -> dict[str, Any]:
    """Exploratory checks, after the registered result: is the null slip the yaw rate times the
    middle pair's offset along x, and does aligning the pairs remove the stall?"""
    base = read_solved(out / "solved_V0.csv")
    stalled = [i for i, r in enumerate(base) if float(r["natural"]) > TARGET]
    converged = [i for i, r in enumerate(base) if float(r["natural"]) <= TARGET]
    ratios = []
    for i in stalled:
        s = states[i]
        _, _, z = axes(s)
        yaw = dot([float(base[i][f"q{k}"]) for k in (3, 4, 5)], z)
        x, _, _ = axes(s)
        dx = dot(sub(s.vec(1, "point"), s.vec(4, "point")), x)
        predicted = abs(yaw * dx) / math.sqrt(2)  # slip difference along (1, -1)/sqrt(2)
        ratios.append(float(base[i]["null_slip"]) / predicted if predicted > 0 else float("nan"))
    report: dict[str, Any] = {"null_slip_over_yaw_times_dx": quantiles(ratios)}
    for name in ("X1", "X2"):
        aligned = out / f"solved_{name}.csv"
        if not aligned.exists():
            continue
        rows = read_solved(aligned)
        report[name] = {
            "resolved": sum(float(rows[i]["natural"]) <= TARGET for i in stalled),
            "broken": sum(float(rows[i]["natural"]) > TARGET for i in converged),
            "S_natural": quantiles([float(rows[i]["natural"]) for i in stalled]),
            "S_null_slip": quantiles([float(rows[i]["null_slip"]) for i in stalled]),
            "S_velocity_change_cm_s": quantiles(
                [
                    max(abs(float(rows[i][f"q{k}"]) - float(base[i][f"q{k}"])) for k in range(3))
                    for i in stalled
                ]
            ),
        }
    return report


def read_states(path: Path) -> list[State]:
    return [State(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_variants(states: list[State], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in VARIANTS:
        rng = random.Random(SEED)
        lines = [variant(s, name, rng).line() for s in states]
        (out / f"states_{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_solved(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def quantiles(values: list[float]) -> dict[str, float]:
    v = sorted(x for x in values if not math.isnan(x))
    if not v:
        return {}
    p90 = v[min(len(v) - 1, int(0.9 * (len(v) - 1) + 0.5))]
    return {"n": len(v), "median": statistics.median(v), "p90": p90, "max": v[-1]}


def summary(states: list[State], stalls_file: Path, out: Path) -> dict[str, Any]:
    solved = {name: read_solved(out / f"solved_{name}.csv") for name in VARIANTS}
    base = solved["V0"]
    stalled = {int(r["line"]) for r in base if float(r["natural"]) > TARGET}
    listed = {int(t) for t in stalls_file.read_text(encoding="utf-8").split()}
    converged = {int(r["line"]) for r in base} - stalled
    windows = {states[i].window for i in stalled}
    matched = {i for i in converged if states[i].window in windows}
    report: dict[str, Any] = {
        "reproduction": {
            "stalled_recomputed": len(stalled),
            "listed": len(listed),
            "only_recomputed": sorted(stalled - listed),
            "only_listed": sorted(listed - stalled),
        },
        "groups": {"S": len(stalled), "W": len(matched), "A": len(converged)},
        "windows_of_S": {w: sum(states[i].window == w for i in stalled) for w in sorted(windows)},
        "wheel_order": wheel_order(states),
    }
    m = [measures(s) for s in states]
    assoc: dict[str, Any] = {}
    for key in m[0]:
        group_s = quantiles([m[i][key] for i in stalled])
        group_w = quantiles([m[i][key] for i in matched])
        group_a = quantiles([m[i][key] for i in converged])
        assoc[key] = {
            "S": group_s,
            "W": group_w,
            "A": group_a,
            "associated": bool(group_s and group_w and group_s["median"] > group_w["p90"]),
        }
    report["measures"] = assoc
    cons: dict[str, Any] = {}
    for label, group in (("S", stalled), ("W", matched), ("A", converged)):
        rows = [base[i] for i in sorted(group)]
        cons[label] = {
            "with_null": sum(int(r["null"]) > 0 for r in rows),
            "null_slip": quantiles([float(r["null_slip"]) for r in rows]),
            "rest_slip": quantiles([float(r["rest_slip"]) for r in rows]),
        }
    masks: dict[str, int] = {}
    for i in stalled:
        bits = int(base[i]["null_wheels"])
        key = "+".join(str(w) for w in range(WHEELS) if bits >> w & 1) or "none"
        masks[key] = masks.get(key, 0) + 1
    cons["S_worst_direction_wheels"] = masks
    report["consistency"] = cons
    effects: dict[str, Any] = {}
    for name in VARIANTS[1:]:
        rows = solved[name]
        resolved = sorted(i for i in stalled if float(rows[i]["natural"]) <= TARGET)
        broken = sorted(i for i in converged if float(rows[i]["natural"]) > TARGET)
        dv = [
            max(abs(float(rows[i][f"q{k}"]) - float(base[i][f"q{k}"])) for k in range(3))
            for i in sorted(stalled)
        ]
        effects[name] = {
            "resolved": len(resolved),
            "broken": len(broken),
            "broken_share": len(broken) / len(converged),
            "S_natural": quantiles([float(rows[i]["natural"]) for i in stalled]),
            "S_velocity_change_cm_s": quantiles(dv),
            "S_with_null": sum(int(rows[i]["null"]) > 0 for i in stalled),
            "S_null_slip": quantiles([float(rows[i]["null_slip"]) for i in stalled]),
        }
    report["variants"] = effects
    report["finding"] = decide(effects, len(stalled), len(converged))
    return report


def passes(e: dict[str, Any], total: int, converged: int) -> bool:
    return bool(e["resolved"] >= 30 * total / 37 and e["broken"] <= 0.01 * converged)


def decide(effects: dict[str, Any], total: int, converged: int) -> dict[str, Any]:
    """The registered rules. The thresholds, 30 and 10 of 37, scale if S's size differs."""
    v4, v6 = effects["V4"], effects["V6"]
    control_ok = v6["resolved"] <= v4["resolved"] / 2
    if passes(v4, total, converged) and control_ok:
        parts = [k for k in ("V1", "V2", "V3") if passes(effects[k], total, converged)]
        finding = "geometry" + (f", mainly {', '.join(parts)}" if parts else ", combined")
    elif v4["resolved"] <= 10 * total / 37:
        finding = "not the geometry"
    else:
        finding = "inconclusive"
    large = v4["S_velocity_change_cm_s"].get("max", 0.0) > 1e-3
    return {"finding": finding, "control_ok": control_ok, "large_correction": large}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "step", choices=("variants", "summary", "explore-variant", "confirm-variant", "explore")
    )
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--stalls", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    states = read_states(args.states)
    if args.step == "variants":
        write_variants(states, args.out)
        print(f"{len(states)} states, {len(VARIANTS)} variants written to {args.out}")
        return 0
    if args.step == "explore-variant":
        lines = [align_pairs(s).line() for s in states]
        (args.out / "states_X1.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0
    if args.step == "confirm-variant":
        # X2, registered after X1: align only pairs whose offset is below 1e-4 cm.
        lines = [align_pairs(s, below=1e-4).line() for s in states]
        (args.out / "states_X2.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0
    if args.step == "explore":
        found = explore(states, args.out)
        (args.out / "explore.json").write_text(json.dumps(found, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(found, indent=2))
        return 0
    if args.stalls is None:
        parser.error("summary needs --stalls")
    report = summary(states, args.stalls, args.out)
    (args.out / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["finding"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
