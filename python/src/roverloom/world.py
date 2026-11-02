"""Loads and checks scenarios, terrain, and rover definitions."""

import math
import random
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from roverloom.api import (
    BaseSite,
    DataWindows,
    DeclaredUncertainty,
    MissionBrief,
    Pose,
    ScienceTarget,
    Target,
)
from roverloom.contract import (
    ContractError,
    JsonDict,
    dump_json,
    load_json_file,
    repo_root,
    sha256_bytes,
    validate,
)

CONTROL_PERIOD_S = 0.5
SIM_STEP_S = 0.1
_ROCK_BUCKET_M = 10.0


@dataclass(frozen=True, slots=True)
class Circle:
    x_m: float
    y_m: float
    radius_m: float

    def contains(self, x: float, y: float, margin: float = 0.0) -> bool:
        return math.hypot(x - self.x_m, y - self.y_m) < self.radius_m + margin


def _circle(spec: JsonDict) -> Circle:
    return Circle(spec["center_xy"][0], spec["center_xy"][1], spec["radius_m"])


def _value_noise_grid(rng: random.Random, nx: int, ny: int) -> list[list[float]]:
    return [[rng.uniform(-1.0, 1.0) for _ in range(nx)] for _ in range(ny)]


def _smooth(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


class Terrain:
    """A heightfield with rocks and soft soil. Ground truth; agents never receive it."""

    def __init__(self, document: JsonDict) -> None:
        validate("terrain", document, document.get("terrain_id", "terrain"))
        self.document = document
        self.terrain_id: str = document["terrain_id"]
        extent = document["extent_m"]
        self.min_x, self.min_y = float(extent["min_xy"][0]), float(extent["min_xy"][1])
        self.max_x, self.max_y = float(extent["max_xy"][0]), float(extent["max_xy"][1])
        if self.min_x >= self.max_x or self.min_y >= self.max_y:
            raise ContractError(f"{self.terrain_id}: extent min must be below max")
        self.spacing: float = document["grid_spacing_m"]
        self.nx = int(math.ceil((self.max_x - self.min_x) / self.spacing)) + 1
        self.ny = int(math.ceil((self.max_y - self.min_y) / self.spacing)) + 1
        if self.nx * self.ny > 4_000_000:
            raise ContractError(f"{self.terrain_id}: terrain grid is too large")
        self.heights = self._generate_heights(document["height"])
        self.rocks = self._generate_rocks(document.get("rocks", {}))
        self.soft_soil = [
            (_circle(s), float(s["slip_fraction"])) for s in document.get("soft_soil", [])
        ]
        self._buckets: dict[tuple[int, int], list[Circle]] = {}
        for rock in self.rocks:
            reach = rock.radius_m
            for bx in range(self._bucket(rock.x_m - reach), self._bucket(rock.x_m + reach) + 1):
                for by in range(self._bucket(rock.y_m - reach), self._bucket(rock.y_m + reach) + 1):
                    self._buckets.setdefault((bx, by), []).append(rock)

    @staticmethod
    def _bucket(value: float) -> int:
        return math.floor(value / _ROCK_BUCKET_M)

    def _generate_heights(self, spec: JsonDict) -> list[list[float]]:
        heights = [[0.0] * self.nx for _ in range(self.ny)]
        if spec["amplitude_m"] == 0:
            return heights
        amplitude = float(spec["amplitude_m"])
        feature = float(spec["feature_size_m"])
        for octave in range(spec["octaves"]):
            rng = random.Random(f"terrain:{spec['seed']}:{octave}")
            cols = int(self.nx * self.spacing / feature) + 3
            rows = int(self.ny * self.spacing / feature) + 3
            lattice = _value_noise_grid(rng, cols, rows)
            for j in range(self.ny):
                v = j * self.spacing / feature
                row, fy = int(v), _smooth(v - int(v))
                for i in range(self.nx):
                    u = i * self.spacing / feature
                    col, fx = int(u), _smooth(u - int(u))
                    a = lattice[row][col] + (lattice[row][col + 1] - lattice[row][col]) * fx
                    b = (
                        lattice[row + 1][col]
                        + (lattice[row + 1][col + 1] - lattice[row + 1][col]) * fx
                    )
                    heights[j][i] += amplitude * (a + (b - a) * fy)
            amplitude /= 2.0
            feature /= 2.0
        return heights

    def _generate_rocks(self, spec: JsonDict) -> list[Circle]:
        rocks = [_circle(r) for r in spec.get("explicit", [])]
        generated = spec.get("generated")
        if generated:
            if generated["min_radius_m"] > generated["max_radius_m"]:
                raise ContractError(f"{self.terrain_id}: rock min radius exceeds max radius")
            clear = [_circle(c) for c in spec.get("keep_clear", [])]
            rng = random.Random(f"rocks:{generated['seed']}")
            for _ in range(generated["count"]):
                x = rng.uniform(self.min_x, self.max_x)
                y = rng.uniform(self.min_y, self.max_y)
                radius = rng.uniform(generated["min_radius_m"], generated["max_radius_m"])
                if not any(c.contains(x, y, radius) for c in clear):
                    rocks.append(Circle(x, y, radius))
        return rocks

    def height_at(self, x: float, y: float) -> float:
        u = min(max((x - self.min_x) / self.spacing, 0.0), self.nx - 1.001)
        v = min(max((y - self.min_y) / self.spacing, 0.0), self.ny - 1.001)
        i, j = int(u), int(v)
        fx, fy = u - i, v - j
        h = self.heights
        a = h[j][i] + (h[j][i + 1] - h[j][i]) * fx
        b = h[j + 1][i] + (h[j + 1][i + 1] - h[j + 1][i]) * fx
        return a + (b - a) * fy

    def slope_along(self, x: float, y: float, yaw: float) -> float:
        """Height change per meter along the heading. Positive means uphill."""
        step = self.spacing / 2.0
        dx, dy = math.cos(yaw) * step, math.sin(yaw) * step
        return (self.height_at(x + dx, y + dy) - self.height_at(x - dx, y - dy)) / (2.0 * step)

    def soil_slip_at(self, x: float, y: float) -> float:
        return max((slip for area, slip in self.soft_soil if area.contains(x, y)), default=0.0)

    def in_bounds(self, x: float, y: float, margin: float = 0.0) -> bool:
        return (
            self.min_x + margin <= x <= self.max_x - margin
            and self.min_y + margin <= y <= self.max_y - margin
        )

    def rocks_near(self, x: float, y: float, reach: float) -> list[Circle]:
        found: dict[int, Circle] = {}
        for bx in range(self._bucket(x - reach), self._bucket(x + reach) + 1):
            for by in range(self._bucket(y - reach), self._bucket(y + reach) + 1):
                for rock in self._buckets.get((bx, by), ()):
                    found[id(rock)] = rock
        return sorted(found.values(), key=lambda r: (r.x_m, r.y_m, r.radius_m))

    def collides(self, x: float, y: float, radius: float) -> bool:
        return any(r.contains(x, y, radius) for r in self.rocks_near(x, y, radius))

    def cast_ray(self, x: float, y: float, angle: float, max_range: float) -> float | None:
        """Return the distance to the nearest rock along a ray, if within range."""
        dx, dy = math.cos(angle), math.sin(angle)
        best: float | None = None
        for rock in self.rocks_near(x + dx * max_range / 2, y + dy * max_range / 2, max_range):
            ox, oy = x - rock.x_m, y - rock.y_m
            b = ox * dx + oy * dy
            disc = b * b - (ox * ox + oy * oy - rock.radius_m * rock.radius_m)
            if disc < 0.0:
                continue
            t = -b - math.sqrt(disc)
            if 0.0 <= t <= max_range and (best is None or t < best):
                best = t
        return best


@dataclass(frozen=True, slots=True)
class RoverSpec:
    document: JsonDict

    def __getattr__(self, name: str) -> Any:
        try:
            return object.__getattribute__(self, "document")[name]
        except KeyError as error:
            raise AttributeError(name) from error


@dataclass(frozen=True)
class Scenario:
    """A validated scenario with its terrain and rover resolved."""

    document: JsonDict
    terrain: Terrain
    rover: RoverSpec

    @property
    def scenario_id(self) -> str:
        return str(self.document["scenario_id"])

    @property
    def seed(self) -> int:
        return int(self.document["seed"])

    @property
    def mission(self) -> JsonDict:
        mission: JsonDict = self.document["mission"]
        return mission

    @cached_property
    def start_pose(self) -> Pose:
        start = Pose.from_dict(self.mission["start_pose"])
        return Pose(
            start.x_m, start.y_m, self.terrain.height_at(start.x_m, start.y_m), start.yaw_rad
        )

    @cached_property
    def targets(self) -> tuple[Target, ...]:
        return tuple(
            Target(o["position_m"][0], o["position_m"][1], o["radius_m"])
            for o in self.mission["objectives"]
        )

    def brief(self) -> MissionBrief:
        return MissionBrief(
            mission_id=self.mission["mission_id"],
            start_pose=self.start_pose,
            targets=self.targets,
            time_limit_s=self.mission["time_limit_s"],
            energy_limit_wh=self.mission.get("energy_limit_wh"),
            control_period_s=self.rover.document.get("control_period_s", CONTROL_PERIOD_S),
            max_speed_mps=self.rover.max_speed_mps,
            max_yaw_rate_radps=self.rover.max_yaw_rate_radps,
            body_radius_m=self.rover.body_radius_m,
            sensor_max_range_m=self.rover.range_sensor["max_range_m"],
            extent_min_xy=(self.terrain.min_x, self.terrain.min_y),
            extent_max_xy=(self.terrain.max_x, self.terrain.max_y),
            can_collect=self._can_collect(),
            battery_capacity_wh=self.rover.battery_capacity_wh,
            declared_uncertainty=self._declared_uncertainty(),
            **self._science_brief(),
        )

    def _can_collect(self) -> bool:
        science = self.mission.get("science") or {}
        return bool(self.rover.document.get("has_sample_tool", True)) and not science.get("survey")

    def _declared_uncertainty(self) -> DeclaredUncertainty | None:
        # Only the declared claim leaves the scenario. The real errors stay hidden.
        uncertainty = self.document.get("uncertainty")
        if uncertainty is None:
            return None
        declared = uncertainty["declared"]
        return DeclaredUncertainty(declared["inspection_noise_sd"], declared["pose_noise_m"])

    def _science_brief(self) -> JsonDict:
        science = self.mission.get("science")
        if science is None:
            return {}
        base, windows = science.get("base"), science.get("data_windows")
        return {
            # true_value is deliberately left out: agents learn it by inspecting.
            "science_targets": tuple(
                ScienceTarget(
                    t["id"],
                    t["position_m"][0],
                    t["position_m"][1],
                    t["radius_m"],
                    t["prior_value"],
                    t["inspect_s"],
                    t["collect_s"],
                )
                for t in science["targets"]
            ),
            "base": BaseSite(
                base["position_m"][0], base["position_m"][1], base["radius_m"], base["required"]
            )
            if base
            else None,
            "data_windows": DataWindows(windows["period_s"], windows["open_s"], windows["offset_s"])
            if windows
            else None,
            "transmit_s_per_item": science["transmit_s_per_item"],
            "success_value": science["success_value"],
        }

    def inputs_sha256(self) -> dict[str, str]:
        return {
            "scenario": _document_hash(self.document),
            "terrain": _document_hash(self.terrain.document),
            "rover": _document_hash(self.rover.document),
        }


def _document_hash(document: JsonDict) -> str:
    return sha256_bytes(dump_json(document).encode("utf-8"))


def build_scenario(document: JsonDict, terrain_doc: JsonDict, rover_doc: JsonDict) -> Scenario:
    """Validate a full set of documents, including checks a schema cannot express."""
    scenario_id = document.get("scenario_id", "scenario")
    validate("scenario", document, scenario_id)
    validate("rover", rover_doc, rover_doc.get("rover_id", "rover"))
    mission = document["mission"]
    if terrain_doc.get("terrain_id") != mission["terrain_id"]:
        raise ContractError(f"{scenario_id}: terrain does not match {mission['terrain_id']}")
    if rover_doc["rover_id"] != document.get("rover_id", "standard_6w"):
        raise ContractError(f"{scenario_id}: rover does not match the scenario")

    terrain = Terrain(terrain_doc)
    radius = rover_doc["body_radius_m"]
    x, y, _ = mission["start_pose"]["position_m"]
    if not terrain.in_bounds(x, y, radius):
        raise ContractError(f"{scenario_id}: start is outside the terrain")
    if terrain.collides(x, y, radius):
        raise ContractError(f"{scenario_id}: start collides with a rock")
    science = mission.get("science")
    if not mission["objectives"] and science is None:
        raise ContractError(f"{scenario_id}: mission needs objectives or a science campaign")
    for index, objective in enumerate(mission["objectives"]):
        tx, ty, _ = objective["position_m"]
        if not terrain.in_bounds(tx, ty, radius):
            raise ContractError(f"{scenario_id}: objective {index} is outside the terrain")
        if terrain.collides(tx, ty, radius):
            raise ContractError(f"{scenario_id}: objective {index} is inside a rock")
    if science is not None:
        _check_science(scenario_id, science, terrain, radius)
    scenario = Scenario(document, terrain, RoverSpec(rover_doc))
    _ = scenario.start_pose  # Rejects a bad start quaternion at load time.
    return scenario


def _check_science(scenario_id: str, science: JsonDict, terrain: Terrain, radius: float) -> None:
    ids = [target["id"] for target in science["targets"]]
    if len(ids) != len(set(ids)):
        raise ContractError(f"{scenario_id}: science target IDs must be unique")
    sites = [(f"science target {t['id']}", t["position_m"]) for t in science["targets"]]
    if "base" in science:
        sites.append(("base", science["base"]["position_m"]))
    for name, (x, y, _) in sites:
        if not terrain.in_bounds(x, y, radius):
            raise ContractError(f"{scenario_id}: {name} is outside the terrain")
        if terrain.collides(x, y, radius):
            raise ContractError(f"{scenario_id}: {name} is inside a rock")
    if science["success_value"] > sum(t["true_value"] for t in science["targets"]):
        raise ContractError(f"{scenario_id}: success_value exceeds the total science value")
    windows = science.get("data_windows")
    if windows and windows["open_s"] > windows["period_s"]:
        raise ContractError(f"{scenario_id}: data window is longer than its period")


def scenario_search_dirs() -> list[Path]:
    root = repo_root()
    return [root / "scenarios" / "practice", root / "scenarios" / "benchmark", root / "scenarios"]


def resolve_scenario_path(name: str) -> Path:
    """Accept a path, or the name of a scenario in the repository."""
    candidate = Path(name)
    if candidate.is_file():
        return candidate
    for directory in scenario_search_dirs():
        path = directory / f"{name}.json"
        if path.is_file():
            return path
    raise ContractError(f"scenario not found: {name}")


def list_practice_scenarios() -> list[str]:
    return sorted(p.stem for p in (repo_root() / "scenarios" / "practice").glob("*.json"))


def load_scenario(name: str, rover: str | None = None) -> Scenario:
    """Load a scenario, optionally replacing its rover with another by name or file path."""
    path = resolve_scenario_path(name)
    document = load_json_file(path)
    validate("scenario", document, name)
    root = repo_root()
    # A terrain beside the scenario comes first, so that private sets can keep theirs private.
    terrain_file = f"{document['mission']['terrain_id']}.json"
    terrain_path = path.parent / "terrains" / terrain_file
    if not terrain_path.is_file():
        terrain_path = root / "scenarios" / "terrains" / terrain_file
    if not terrain_path.is_file():
        raise ContractError(f"{name}: unknown terrain {document['mission']['terrain_id']}")
    from roverloom.rover_builder import load_rover_document

    rover_doc = load_rover_document(rover or document.get("rover_id", "standard_6w"))
    document = {**document, "rover_id": rover_doc["rover_id"]}
    return build_scenario(document, load_json_file(terrain_path), rover_doc)
