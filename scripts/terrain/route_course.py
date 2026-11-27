"""Route a race course on a site heightfield, and draw a map of it.

Flags are given in the site frame (metres east and north of the rover's start). Between two flags the path is
found by A* on a 2 m lattice over the 4 m-baseline slope, refusing any point whose slope, or whose neighbours'
within 3 m, reaches the limit; then straight shortcuts are taken wherever every metre of them stays under it.
A flag on steep ground is moved to the nearest clear point within 10 m. The output is the path that
python/src/roverloom/race.py stores for the course.

    python3 scripts/terrain/route_course.py --site noctis --flags "0,0 40,-10 ... 0,0" --map runs/noctis.png

Needs NumPy, and Pillow for --map. Reads unreal/Saved/Terrain/<site>/<site>_site.r16 and .json (hirise_site.py).
Slopes are from the DTM; the 1 m posts are interpolated, and the Unreal rover's limits on slopes are not measured
here. Nothing about traversability on Mars is claimed.
"""

# ruff: noqa: E501  (long prose lines in the docstring; wrapping them would not help the reader)

from __future__ import annotations

import argparse
import heapq
import json
import math
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
SITES = json.loads(Path(__file__).with_name("sites.json").read_text())
SAMPLES = 1009
BLOCK = 4  # 4 m baseline, as hirise_site.py


class Terrain:
    def __init__(self, site: str):
        data = REPO / "unreal/Saved/Terrain" / site
        info = json.loads((data / f"{site}_site.json").read_text())
        raw = np.fromfile(data / f"{site}_site.r16", dtype="<u2").reshape(SAMPLES, SAMPLES)
        low, high = info["height_min_m"], info["height_max_m"]
        self.height = low + raw.astype(np.float64) / 65535.0 * (high - low)
        east, north = SITES[site]["origin_m"]
        # Site frame (x east, y north, origin at the start) to grid (row 0 north)
        self.col0 = (SAMPLES - 1) / 2 + east
        self.row0 = (SAMPLES - 1) / 2 - north
        n = (SAMPLES - 1) // BLOCK
        pooled = self.height[: n * BLOCK, : n * BLOCK].reshape(n, BLOCK, n, BLOCK).mean(axis=(1, 3))
        gy, gx = np.gradient(pooled, float(BLOCK))
        self.slope4 = np.degrees(np.arctan(np.hypot(gx, gy)))

    def rc(self, x: float, y: float) -> tuple[float, float]:
        return self.row0 - y, self.col0 + x

    def slope(self, x: float, y: float) -> float:
        r, c = self.rc(x, y)
        n = self.slope4.shape[0] - 1
        return float(self.slope4[min(n, max(0, int(r) // BLOCK)), min(n, max(0, int(c) // BLOCK))])

    def clear(self, x: float, y: float) -> float:
        """The steepest 4 m slope within 3 m: the rover is about 2.5 m wide."""
        return max(self.slope(x + dx, y + dy) for dx in (-3, 0, 3) for dy in (-3, 0, 3))

    def height_at(self, x: float, y: float) -> float:
        r, c = self.rc(x, y)
        return float(self.height[int(round(r)), int(round(c))])


def snap(t: Terrain, flag: tuple[float, float], limit: float) -> tuple[float, float]:
    best = None
    for dx in range(-10, 11):
        for dy in range(-10, 11):
            p = (flag[0] + dx, flag[1] + dy)
            if t.clear(*p) < limit - 2 and (best is None or dx * dx + dy * dy < best[0]):
                best = (dx * dx + dy * dy, p)
    if best is None:
        raise SystemExit(f"no clear ground within 10 m of flag {flag}")
    return best[1]


def astar(t: Terrain, a: tuple[float, float], b: tuple[float, float], limit: float):
    step = 2
    start = tuple(int(round(v)) for v in a)
    goal = tuple(int(round(v)) for v in b)
    frontier = [(0.0, start)]
    cost = {start: 0.0}
    came: dict[tuple[int, int], tuple[int, int]] = {}
    moves = [(dx * step, dy * step) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
    reached = None
    while frontier:
        _, u = heapq.heappop(frontier)
        if abs(u[0] - goal[0]) <= step and abs(u[1] - goal[1]) <= step:
            reached = u
            break
        for dx, dy in moves:
            v = (u[0] + dx, u[1] + dy)
            r, c = t.rc(*v)
            if not (8 <= r < SAMPLES - 8 and 8 <= c < SAMPLES - 8):
                continue
            s = t.clear(*v)
            if s >= limit:
                continue
            nd = cost[u] + (1 + 3 * (s / limit) ** 2) * math.hypot(dx, dy)
            if nd < cost.get(v, math.inf):
                cost[v] = nd
                came[v] = u
                heapq.heappush(frontier, (nd + math.dist(v, goal), v))
    if reached is None:
        raise SystemExit(f"no route from {a} to {b} under {limit} degrees")
    path = [reached]
    while path[-1] != start:
        path.append(came[path[-1]])
    return [(float(x), float(y)) for x, y in reversed(path)]


def segment_ok(t: Terrain, a, b, limit: float) -> bool:
    n = int(math.dist(a, b)) + 1
    return all(
        t.clear(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) < limit
        for k in range(n + 1)
    )


def shortcut(t: Terrain, points, limit: float):
    out, i = [points[0]], 0
    while i < len(points) - 1:
        j = len(points) - 1
        while j > i + 1 and not segment_ok(t, points[i], points[j], limit):
            j -= 1
        out.append(points[j])
        i = j
    return out


def route(t: Terrain, flags, limit: float):
    flags = [flags[0], *[snap(t, f, limit) for f in flags[1:-1]], flags[-1]]
    path = [flags[0]]
    for a, b in zip(flags, flags[1:], strict=False):
        leg = astar(t, a, b, limit)
        leg[0], leg[-1] = a, b
        path += shortcut(t, leg, limit)[1:]
    return flags, path


def draw(t: Terrain, path, flags, target: Path) -> None:
    from PIL import Image, ImageDraw

    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    x0, x1, y0, y1 = min(xs) - 40, max(xs) + 40, min(ys) - 40, max(ys) + 40
    k = 4
    r0, c0 = (int(v) for v in t.rc(x0, y1))
    r1, c1 = (int(v) for v in t.rc(x1, y0))
    h = t.height[max(0, r0) : r1, max(0, c0) : c1]
    gy, gx = np.gradient(h, 1.0)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    shade = np.sin(0.7) * np.cos(slope) + np.cos(0.7) * np.sin(slope) * np.cos(
        math.radians(315) - aspect
    )
    grey = np.clip(shade * 200 + 35, 0, 255)
    rgb = np.stack([grey * 1.0, grey * 0.72, grey * 0.52], -1)
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).resize(
        (h.shape[1] * k, h.shape[0] * k)
    )
    d = ImageDraw.Draw(img)

    def px(p):
        return ((p[0] - x0) * k, (y1 - p[1]) * k)

    d.line([px(p) for p in path], fill=(255, 255, 255), width=4)
    for i, f in enumerate(flags[1:], 1):
        x, y = px(f)
        d.line([x, y, x, y - 30], fill=(250, 250, 245), width=3)
        d.polygon([(x, y - 30), (x + 20, y - 24), (x, y - 18)], fill=(235, 95, 25))
        d.text((x + 5, y - 16), str(i), fill=(255, 255, 255))
    x, y = px(flags[0])
    d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=(20, 20, 20), outline=(255, 255, 255), width=2)
    target.parent.mkdir(parents=True, exist_ok=True)
    img.save(target)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--site", choices=sorted(k for k in SITES if not k.startswith("_")), required=True
    )
    parser.add_argument("--flags", required=True, help='"x,y x,y ..." in metres, start first')
    parser.add_argument("--limit-deg", type=float, default=10.0)
    parser.add_argument("--map", type=Path)
    args = parser.parse_args()
    terrain = Terrain(args.site)
    flags = [tuple(float(v) for v in item.split(",")) for item in args.flags.split()]
    flags, path = route(terrain, flags, args.limit_deg)
    length = sum(math.dist(a, b) for a, b in zip(path, path[1:], strict=False))
    worst = max(
        terrain.slope(a[0] + (b[0] - a[0]) * k / 20, a[1] + (b[1] - a[1]) * k / 20)
        for a, b in zip(path, path[1:], strict=False)
        for k in range(21)
    )
    rise = [round(terrain.height_at(*f) - terrain.height_at(*flags[0]), 1) for f in flags]
    print(
        json.dumps(
            {
                "site": args.site,
                "flags": [list(f) for f in flags],
                "path": [list(p) for p in path],
                "length_m": round(length, 1),
                "steepest_on_path_deg": round(worst, 1),
                "flag_heights_m": rise,
                "start_slope_deg": round(terrain.clear(*flags[0]), 1),
            }
        )
    )
    if args.map:
        draw(terrain, path, flags, args.map)


if __name__ == "__main__":
    main()
