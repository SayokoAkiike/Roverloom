"""Compiles rover designs into rover parameters, and enforces design budgets.

Every formula here is a simplified game rule, chosen so that design choices have clear trade-offs.
None of them is a validated wheel, soil, or power model. See docs/rover-builder.md.
"""

import json
import math
from pathlib import Path

from roverloom.contract import ContractError, JsonDict, load_json_file, repo_root, validate

BUILDER_VERSION = "builder-0.2"
MAX_MASS_KG = 1600.0
MAX_COST = 100.0
# Entries compete only inside a class, so that spending more is not by itself a way to win.
DESIGN_CLASSES = {
    "light": {"max_cost": 40.0, "max_mass_kg": 600.0},
    "standard": {"max_cost": 70.0, "max_mass_kg": 1000.0},
    "heavy": {"max_cost": MAX_COST, "max_mass_kg": MAX_MASS_KG},
}
_VOLUME_L_PER_CHASSIS_KG = 0.5
_BATTERY_DISCHARGE_PER_H = 2.0
_ARM_MIN_CHASSIS_KG = 250.0
_RTG_MIN_CHASSIS_KG = 400.0
_INSTRUMENT_W = 100.0
_ARM_TASK_FACTOR = 3.0
_TRANSMIT_TASK_FACTOR = 1.5
_REFERENCE_PRESSURE_PA = 6000.0
_MARS_GRAVITY = 3.71
_CRAWL_MPS = 0.15

WHEEL_LAYOUTS = {
    4: ("front_left", "front_right", "rear_left", "rear_right"),
    6: ("front_left", "front_right", "middle_left", "middle_right", "rear_left", "rear_right"),
    8: (
        "front_left",
        "front_right",
        "middle_left",
        "middle_right",
        "middle2_left",
        "middle2_right",
        "rear_left",
        "rear_right",
    ),
}
_COMPUTE = {
    "low": {"period": 1.0, "power": 20.0, "mass": 5.0, "cost": 2.0, "volume": 5.0, "beams": 9},
    "standard": {
        "period": 0.5,
        "power": 60.0,
        "mass": 10.0,
        "cost": 6.0,
        "volume": 10.0,
        "beams": 21,
    },
    "high": {
        "period": 0.2,
        "power": 150.0,
        "mass": 20.0,
        "cost": 14.0,
        "volume": 20.0,
        "beams": 32,
    },
}
_POSE_GRADE = {
    "basic": {"noise": 1.5, "cost": 1.0},
    "standard": {"noise": 1.0, "cost": 4.0},
    "precise": {"noise": 0.5, "cost": 10.0},
}
_LIMITS = {
    "radius": (0.1, 0.6),
    "width": (0.05, 0.5),
    "motor": (10.0, 500.0),
    "chassis": (100.0, 1500.0),
    "battery": (50.0, 4000.0),
    "panel": (0.5, 20.0),
    "rtg": (10.0, 400.0),
    "range": (2.0, 60.0),
    "beams": (1, 32),
    "fov": (0.2, 6.2),
}


def _in_range(design_id: str, name: str, key: str, value: float) -> None:
    low, high = _LIMITS[key]
    if not low <= value <= high:
        raise ContractError(f"{design_id}: {name} {value} is outside {low} to {high}")


def design_class(cost: float, mass_kg: float) -> str:
    """The smallest class whose budgets a design fits."""
    for name, limits in DESIGN_CLASSES.items():
        if cost <= limits["max_cost"] and mass_kg <= limits["max_mass_kg"]:
            return name
    raise ContractError(f"cost {cost:.1f} and mass {mass_kg:.0f} kg fit no design class")


def _wheel_geometry(count: int, radius: float, width: float, body_radius: float) -> list[JsonDict]:
    """Wheel centers in the body frame: +X forward, +Y left, +Z up, origin on the ground."""
    rows = count // 2
    wheels: list[JsonDict] = []
    for index, name in enumerate(WHEEL_LAYOUTS[count]):
        row = index // 2
        x = 0.8 * body_radius * (1.0 - 2.0 * row / (rows - 1))
        y = 0.85 * body_radius * (1.0 if name.endswith("_left") else -1.0)
        wheels.append(
            {
                "wheel_id": name,
                "position_m": [round(x, 4), round(y, 4), radius],
                "radius_m": radius,
                "width_m": width,
            }
        )
    return wheels


def compile_design(design: JsonDict) -> JsonDict:
    """Return rover parameters for a design, or raise listing every rule the design breaks."""
    design_id = design.get("design_id", "design")
    validate("rover_design", design, design_id)
    wheels, sensors, power = design["wheels"], design["sensors"], design["power"]
    count, radius, width = wheels["count"], wheels["radius_m"], wheels["width_m"]
    motor = wheels["motor_w"]
    _in_range(design_id, "wheel radius", "radius", radius)
    _in_range(design_id, "wheel width", "width", width)
    _in_range(design_id, "motor power", "motor", motor)
    _in_range(design_id, "chassis mass", "chassis", design["chassis_kg"])
    _in_range(design_id, "battery", "battery", design["battery_wh"])
    _in_range(design_id, "range sensor", "range", sensors["range_max_m"])
    _in_range(design_id, "range beams", "beams", sensors["range_beams"])
    _in_range(design_id, "range field of view", "fov", sensors["range_fov_rad"])

    panel_m2 = power["panel_m2"] if power["kind"] == "solar" else 0.0
    rtg_w = power["output_w"] if power["kind"] == "rtg" else 0.0
    if power["kind"] == "solar":
        _in_range(design_id, "solar panel", "panel", panel_m2)
    if power["kind"] == "rtg":
        _in_range(design_id, "RTG output", "rtg", rtg_w)

    compute = _COMPUTE[design["compute"]]
    grade = _POSE_GRADE[sensors["pose_grade"]]
    arm = design["tools"]["sample_arm"]
    beams, sensor_range = sensors["range_beams"], sensors["range_max_m"]

    mass_parts = {
        "chassis": design["chassis_kg"],
        "wheels": count * 25.0 * (radius / 0.25) ** 2 * (width / 0.2),
        "motors": count * motor * 0.04,
        "battery": design["battery_wh"] / 4.0,
        "power": panel_m2 * 10.0 + rtg_w * 0.45,
        "sensors": 5.0 + beams * 0.5 + sensor_range * 0.2,
        "compute": compute["mass"],
        "tools": 60.0 if arm else 0.0,
    }
    cost_parts = {
        "chassis": design["chassis_kg"] * 0.01,
        "wheels": count * 1.2 + count * motor * 0.01,
        "battery": design["battery_wh"] * 0.012,
        "power": panel_m2 * 1.5 + rtg_w * 0.25,
        "sensors": beams * 0.6 + sensor_range * 0.3 + grade["cost"],
        "compute": compute["cost"],
        "tools": 8.0 if arm else 0.0,
    }
    volume_parts = {
        "battery": design["battery_wh"] * 0.2,
        "motors": count * motor * 0.03,
        "power": rtg_w * 0.2,
        "sensors": 5.0 + beams,
        "compute": compute["volume"],
        "tools": 40.0 if arm else 0.0,
    }
    mass = sum(mass_parts.values())
    cost = sum(cost_parts.values())
    volume = sum(volume_parts.values())
    volume_capacity = design["chassis_kg"] * _VOLUME_L_PER_CHASSIS_KG
    idle = 150.0 + beams * 3.0 + sensor_range * 2.0 + compute["power"]
    task_factor = _ARM_TASK_FACTOR if arm else _TRANSMIT_TASK_FACTOR
    peak_power = idle + max(count * motor, _INSTRUMENT_W * task_factor)
    peak_limit = design["battery_wh"] * _BATTERY_DISCHARGE_PER_H
    weight = mass * _MARS_GRAVITY
    pressure = weight / (count * 2.0 * radius * width)
    structure_needed = 0.2 * (mass - mass_parts["chassis"])

    problems: list[str] = []
    if mass > MAX_MASS_KG:
        problems.append(f"mass {mass:.0f} kg exceeds {MAX_MASS_KG:.0f} kg")
    if cost > MAX_COST:
        problems.append(f"cost {cost:.1f} exceeds {MAX_COST:.0f}")
    if design["chassis_kg"] < structure_needed:
        problems.append(
            f"chassis {design['chassis_kg']} kg cannot carry its parts; "
            f"needs at least {structure_needed:.0f} kg"
        )
    if pressure > 3.0 * _REFERENCE_PRESSURE_PA:
        problems.append(f"ground pressure {pressure:.0f} Pa is too high to drive")
    if volume > volume_capacity:
        problems.append(f"parts need {volume:.0f} L but the chassis holds {volume_capacity:.0f} L")
    if peak_power > peak_limit:
        problems.append(
            f"peak load {peak_power:.0f} W exceeds the {peak_limit:.0f} W the battery can deliver"
        )
    if beams > compute["beams"]:
        problems.append(
            f"{design['compute']} compute handles {compute['beams']} range beams, not {beams}"
        )
    if sensors["pose_grade"] == "precise" and design["compute"] == "low":
        problems.append("precise pose estimation is incompatible with low compute")
    if arm and design["chassis_kg"] < _ARM_MIN_CHASSIS_KG:
        problems.append(f"a sample arm needs a chassis of at least {_ARM_MIN_CHASSIS_KG:.0f} kg")
    if rtg_w > 0 and design["chassis_kg"] < _RTG_MIN_CHASSIS_KG:
        problems.append(f"an RTG needs a chassis of at least {_RTG_MIN_CHASSIS_KG:.0f} kg")
    if problems:
        raise ContractError(f"{design_id}: " + "; ".join(problems))

    relative_pressure = pressure / _REFERENCE_PRESSURE_PA
    rolling = 0.10 + 0.05 * relative_pressure
    efficiency = 0.6
    motor_speed = count * motor * efficiency / (weight * rolling)
    speed = min(2.0 * radius, motor_speed)
    # Climbing is judged at a crawl, where motors can trade speed for force.
    climb = max(0.1, min(0.9, count * motor * efficiency / (weight * _CRAWL_MPS) - rolling))
    body_radius = 0.5 + 0.12 * count
    if radius * 2.0 > body_radius * 2.0:
        raise ContractError(f"{design_id}: wheels are larger than the body")

    fov = sensors["range_fov_rad"]
    bearings = (
        [0.0] if beams == 1 else [round(-fov / 2 + fov * i / (beams - 1), 4) for i in range(beams)]
    )
    solar_w = panel_m2 * 60.0  # Game value: nominal electrical output per square meter.
    report: JsonDict = {
        "builder_version": BUILDER_VERSION,
        "design_version": design["version"],
        "mass_kg": round(mass, 2),
        "mass_parts_kg": {k: round(v, 2) for k, v in mass_parts.items()},
        "cost": round(cost, 2),
        "cost_parts": {k: round(v, 2) for k, v in cost_parts.items()},
        "design_class": design_class(cost, mass),
        "volume_l": round(volume, 1),
        "volume_capacity_l": round(volume_capacity, 1),
        "peak_power_w": round(peak_power, 1),
        "peak_power_limit_w": round(peak_limit, 1),
        "net_idle_power_w": round(solar_w + rtg_w - idle, 1),
        # Which part sets each limit, so that a result can be traced back to a design choice.
        "limited_by": {
            "speed": "motor_power" if motor_speed < 2.0 * radius else "wheel_radius",
            "control_rate": "compute",
            "endurance": "generation" if solar_w + rtg_w >= idle else "battery",
        },
        "ground_pressure_pa": round(pressure, 1),
        "simplified_model": True,
    }
    rover: JsonDict = {
        "schema_version": 0,
        "rover_id": design["design_id"],
        "version": design["version"],
        "description": design["description"],
        "mass_kg": round(mass, 3),
        "body_radius_m": round(body_radius, 3),
        "wheel_radius_m": radius,
        "max_speed_mps": round(speed, 4),
        "max_yaw_rate_radps": round(min(0.8, 0.6 / body_radius), 4),
        "max_accel_mps2": round(max(0.05, 0.25 * math.sqrt(1000.0 / mass)), 4),
        "max_yaw_accel_radps2": 0.5,
        "max_climb_slope": round(climb, 4),
        "battery_capacity_wh": design["battery_wh"],
        "idle_power_w": round(idle, 2),
        "rolling_resistance": round(rolling, 4),
        "drive_efficiency": efficiency,
        "turn_power_w_per_radps": round(mass * 0.2, 2),
        "base_slip_fraction": round(0.01 + 0.02 * relative_pressure, 4),
        "slope_slip_factor": 0.5,
        "slip_noise": 0.01,
        "failed_wheel_yaw_bias_radps": round(0.48 / count, 4),
        "range_sensor": {"max_range_m": sensor_range, "bearings_rad": bearings},
        "wheels": list(WHEEL_LAYOUTS[count]),
        "soil_slip_scale": round(max(0.5, min(1.5, relative_pressure)), 4),
        "solar_panel_w": round(solar_w, 2),
        "rtg_w": rtg_w,
        "control_period_s": compute["period"],
        "pose_noise_scale": grade["noise"],
        "has_sample_tool": arm,
        "instrument_power_w": _INSTRUMENT_W,
        "geometry": {
            "frame": "body_flu",
            "wheels": _wheel_geometry(count, radius, width, body_radius),
        },
        "design_report": report,
    }
    validate("rover", rover, design_id)
    return rover


_INTERVENTIONS: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("motor power +25%", ("wheels", "motor_w"), 1.25),
    ("wheel radius +25%", ("wheels", "radius_m"), 1.25),
    ("wheel width +25%", ("wheels", "width_m"), 1.25),
    ("battery +25%", ("battery_wh",), 1.25),
    ("chassis +25%", ("chassis_kg",), 1.25),
    ("sensor range +25%", ("sensors", "range_max_m"), 1.25),
)
_TRACKED = ("max_speed_mps", "max_climb_slope", "soil_slip_scale", "idle_power_w")


def explain_design(design: JsonDict) -> list[JsonDict]:
    """Change one part at a time, and report what each change does to cost and performance.

    A change the builder refuses is reported with the reason, since that is also a design fact.
    """
    base = compile_design(design)
    rows: list[JsonDict] = []
    for label, path, factor in _INTERVENTIONS:
        variant = json.loads(json.dumps(design))
        node = variant
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] *= factor
        try:
            changed = compile_design(variant)
        except ContractError as error:
            rows.append({"change": label, "refused": str(error).split(": ", 1)[-1]})
            continue
        report, base_report = changed["design_report"], base["design_report"]
        rows.append(
            {
                "change": label,
                "cost": round(report["cost"] - base_report["cost"], 2),
                "mass_kg": round(report["mass_kg"] - base_report["mass_kg"], 1),
                **{key: round(changed[key] - base[key], 3) for key in _TRACKED},
            }
        )
    return rows


def designs_dir() -> Path:
    return repo_root() / "rovers" / "designs"


def list_designs() -> list[str]:
    return sorted(path.stem for path in designs_dir().glob("*.json"))


def require_design(name: str) -> None:
    """Refuse plain rover parameters where budgets matter: they would bypass every rule."""
    if "design_report" not in load_rover_document(name):
        raise ContractError(f"{name}: must be a rover design, not plain parameters")


def load_rover_document(name: str) -> JsonDict:
    """Load a rover by name or file path. Designs are compiled, and parameters used directly."""
    path = Path(name)
    if not path.is_file():
        design = designs_dir() / f"{name}.json"
        path = design if design.is_file() else repo_root() / "rovers" / f"{name}.json"
    if not path.is_file():
        raise ContractError(f"unknown rover: {name}")
    document = load_json_file(path)
    if "design_id" in document:
        return compile_design(document)
    validate("rover", document, name)
    return document
