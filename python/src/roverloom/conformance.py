"""Checks that a backend's run logs obey the shared contract. Works on any backend's files.

Schemas catch wrong shapes. These checks catch what schemas cannot: wrong units, a mirrored frame,
and time that does not advance as declared. A log can pass and still be physically unrealistic.
"""

import math
from pathlib import Path

from roverloom.contract import JsonDict
from roverloom.frames import quat_to_yaw
from roverloom.runlog import load_run

_MIN_SPEED_MPS = 0.05
_DISTANCE_TOLERANCE = 0.25
_HEADING_TOLERANCE_RAD = 0.5
_YAW_TOLERANCE_RAD = 0.2


def _unit_quaternion(q: list[float]) -> bool:
    return abs(math.sqrt(sum(c * c for c in q)) - 1.0) < 0.01


def check_run_contract(directory: Path) -> list[str]:
    """Return every contract problem found in a finished run. An empty list means none."""
    run = load_run(directory)  # Checks schemas, hashes, ordering, and the final event.
    problems: list[str] = []
    step = float(run.manifest["sim_step_s"])
    telemetry = run.telemetry
    moved_ok = heading_ok = yaw_ok = samples = 0
    moved_bad = heading_bad = yaw_bad = 0
    previous: JsonDict | None = None
    for record in telemetry:
        orientation = record["pose"]["orientation_xyzw"]
        if not _unit_quaternion(orientation):
            problems.append(f"t={record['time_s']}: orientation is not a unit quaternion")
        if not 0.0 <= record["battery_fraction"] <= 1.0:
            problems.append(f"t={record['time_s']}: battery fraction is outside 0 to 1")
        if previous is not None:
            dt = record["time_s"] - previous["time_s"]
            if abs(dt - step) > 1e-6:
                problems.append(f"t={record['time_s']}: step is {dt}, manifest says {step}")
            ax, ay, _ = previous["pose"]["position_m"]
            bx, by, _ = record["pose"]["position_m"]
            vx, vy, _ = record["linear_velocity_mps"]
            speed = math.hypot(vx, vy)
            samples += 1
            if speed >= _MIN_SPEED_MPS:
                # Position and velocity must agree as vectors. Centimeters would differ a
                # hundredfold, and a mirrored axis would point the wrong way.
                gap = math.hypot(bx - ax - vx * dt, by - ay - vy * dt)
                if gap <= max(_DISTANCE_TOLERANCE * speed * dt, 1e-3):
                    moved_ok += 1
                else:
                    moved_bad += 1
                # Frame: a rover drives along its heading, so a mirrored Y shows up here.
                yaw = quat_to_yaw(tuple(orientation))
                error = abs((math.atan2(vy, vx) - yaw + math.pi) % (2.0 * math.pi) - math.pi)
                reverse = abs(error - math.pi)
                if min(error, reverse) <= _HEADING_TOLERANCE_RAD:
                    heading_ok += 1
                else:
                    heading_bad += 1
            # Handedness: a positive yaw rate must increase yaw.
            rate = record["yaw_rate_radps"]
            if abs(rate) > 0.05:
                before = quat_to_yaw(tuple(previous["pose"]["orientation_xyzw"]))
                after = quat_to_yaw(tuple(orientation))
                change = (after - before + math.pi) % (2.0 * math.pi) - math.pi
                if abs(change - rate * dt) <= max(_YAW_TOLERANCE_RAD * abs(rate) * dt, 1e-3):
                    yaw_ok += 1
                else:
                    yaw_bad += 1
        previous = record
    if moved_bad > moved_ok:
        problems.append(
            f"position and velocity disagree in {moved_bad} samples; check the units and the frame"
        )
    if heading_bad > heading_ok:
        problems.append(
            f"motion is not along the heading in {heading_bad} samples; check the frame"
        )
    if yaw_bad > yaw_ok:
        problems.append(f"yaw does not follow yaw rate in {yaw_bad} samples; check its sign")
    if not samples and len(telemetry) > 1:
        problems.append("telemetry has no usable samples")
    return problems
