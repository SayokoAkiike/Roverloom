"""Check a raced run for rovers that overlap, as judged in Python and as drawn in Unreal.

`states.jsonl` holds what Python judged at each telemetry message. `unreal.log` holds `RaceDraw`
lines: where Unreal drew the player's body and each rival at the same moment. Both are checked with
the race's rover rectangles, so a difference between them points at the Unreal side.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from roverloom.race import COUNTDOWN_S, MODEL_VERSION, RULESET, Racer, overlap

DRAW = re.compile(r"RaceDraw t=(-?[\d.]+) you=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)((?: \S+@[-\d.,]+)*)")
MODEL = re.compile(r"Rover model: (V2|greybox)[^\n]*")


@dataclass
class Sample:
    t: float
    you: tuple[float, float, float]
    rivals: dict[str, tuple[float, float, float]]


@dataclass
class Contact:
    t: float
    rival: str
    depth: float  # > 0: the rectangles overlap by this much
    ahead: float  # rival's centre in the player's frame, metres
    left: float


def newest_run(parent: Path) -> Path:
    runs = sorted(
        (p for p in parent.glob("run-*") if (p / "states.jsonl").exists()),
        key=lambda p: p.stat().st_mtime,
    )
    if not runs:
        raise ValueError(f"no race runs under {parent}")
    return runs[-1]


def python_samples(path: Path) -> tuple[list[Sample], set[str], dict[str, str]]:
    samples, rules, names = [], set(), {}
    last: tuple[float, float] | None = None
    yaw = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        s = json.loads(line)
        rules.add(f"{s.get('ruleset')} / {s.get('model_version')}")
        x, y = float(s["position_m"][0]), float(s["position_m"][1])
        if isinstance(s.get("yaw_rad"), (int, float)):
            yaw = float(s["yaw_rad"])
        elif last and math.dist(last, (x, y)) > 0.05:  # older runs: heading from motion
            yaw = math.atan2(y - last[1], x - last[0])
        if not last or math.dist(last, (x, y)) > 0.05:
            last = (x, y)
        rivals = {}
        for o in s.get("race", {}).get("opponents", []):
            if o.get("kind") == "ghost":
                continue
            names[o["id"]] = o.get("name", o["id"])
            rivals[o["id"]] = (o["position_m"][0], o["position_m"][1], o.get("yaw_rad", 0.0))
        samples.append(Sample(float(s.get("time_s", 0.0)), (x, y, yaw), rivals))
    return samples, rules, names


def drawn_samples(log: str) -> list[Sample]:
    out = []
    for m in DRAW.finditer(log):
        rivals = {}
        for part in m.group(5).split():
            rid, _, xyz = part.partition("@")
            x, y, yaw = (float(v) for v in xyz.split(","))
            rivals[rid] = (x, y, yaw)
        you = (float(m.group(2)), float(m.group(3)), float(m.group(4)))
        # Unreal's clock starts with the countdown, the race clock after it
        out.append(Sample(float(m.group(1)) - COUNTDOWN_S, you, rivals))
    return out


def contacts(samples: Iterable[Sample]) -> Iterator[Contact]:
    for s in samples:
        you = Racer("you", "You", "you", {}, *s.you)
        for rid, (x, y, yaw) in s.rivals.items():
            other = Racer(rid, rid, "npc", {}, x, y, yaw)
            dx, dy = x - you.x, y - you.y
            ahead = dx * math.cos(you.yaw) + dy * math.sin(you.yaw)
            left = -dx * math.sin(you.yaw) + dy * math.cos(you.yaw)
            hit = overlap(you, other, gap=0.0)
            if hit is not None:
                yield Contact(s.t, rid, hit[0], ahead, left)
            elif math.hypot(dx, dy) < 4.5:
                yield Contact(s.t, rid, -_clearance(you, other), ahead, left)


def _clearance(a: Racer, b: Racer) -> float:
    """Smallest gap between the rectangles, to a centimetre (bisection on the gap)."""
    lo, hi = 0.0, 3.0
    while hi - lo > 0.01:
        mid = (lo + hi) / 2
        if overlap(a, b, gap=mid) is None:
            lo = mid
        else:
            hi = mid
    return lo


def where(c: Contact) -> str:
    side = "left" if c.left > 0 else "right"
    if c.ahead < -1.0:
        place = f"behind ({-c.ahead:.1f} m back, {abs(c.left):.1f} m {side})"
    elif c.ahead > 1.0:
        place = f"ahead ({c.ahead:.1f} m, {abs(c.left):.1f} m {side})"
    else:
        place = f"beside ({abs(c.left):.1f} m {side})"
    return place


def summarize(label: str, samples: list[Sample], names: dict[str, str]) -> tuple[list[str], int]:
    found = list(contacts(samples))
    hits = [c for c in found if c.depth > 0]
    lines = [f"{label}: {len(samples)} samples, rovers overlap in {len(hits)}."]
    picked: list[Contact] = []
    for c in sorted(found, key=lambda c: -c.depth):
        if all(abs(c.t - p.t) > 1.0 or c.rival != p.rival for p in picked):
            picked.append(c)
        if len(picked) == 5:
            break
    for c in picked:
        state = f"overlap {c.depth:.2f} m" if c.depth > 0 else f"gap {-c.depth:.2f} m"
        lines.append(f"  t={c.t:7.2f}s  {names.get(c.rival, c.rival):12} {state:16} {where(c)}")
    return lines, len(hits)


def report(run: Path) -> str:
    lines = [f"Run: {run}"]
    states = run / "states.jsonl"
    if not states.exists():
        raise ValueError(f"{states} not found")
    samples, rules, names = python_samples(states)
    current = f"{RULESET} / {MODEL_VERSION}"
    lines.append(f"Race rules in this run: {', '.join(sorted(rules))} (this checkout: {current})")
    log_path = run / "unreal.log"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    model = MODEL.search(log)
    lines.append(f"Rover model in Unreal: {model.group(0) if model else 'not in unreal.log'}")
    py_lines, py_hits = summarize("Python's positions (states.jsonl)", samples, names)
    lines += py_lines
    drawn = drawn_samples(log)
    if drawn:
        draw_lines, draw_hits = summarize("Drawn in Unreal (unreal.log RaceDraw)", drawn, names)
        lines += draw_lines
    else:
        draw_hits = -1
        lines.append("Drawn in Unreal: no RaceDraw lines (the C++ is older; rebuild with --build).")
    shots = sorted(p.name for p in run.glob("contact-*.png"))
    if shots:
        lines.append(f"Screenshots at close contact: {', '.join(shots)}")
    movie = run / "race.mov"
    if movie.exists():
        lines.append(f"Video: {movie} ({movie.stat().st_size / 1e6:.0f} MB)")
    lines.append("Verdict: " + verdict(rules, current, py_hits, draw_hits))
    return "\n".join(lines)


def verdict(rules: set[str], current: str, py_hits: int, draw_hits: int) -> str:
    if rules != {current}:
        return "this run used other race rules than this checkout; run `git pull` and race again."
    if py_hits:
        return "Python let rovers overlap: a bug in the race rules."
    if draw_hits > 0:
        return (
            "Python kept rovers apart, but Unreal drew them overlapping: a drawing or timing bug."
        )
    if draw_hits == 0:
        return "no overlap in Python or in Unreal's drawn positions; compare the screenshots."
    return "no overlap in Python; Unreal's drawn positions were not logged."
