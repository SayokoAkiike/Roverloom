"""Coordinate, unit, and rotation conventions, and conversions between them.

The contract frame is the site frame: right-handed, +X east, +Y north, +Z up, in SI units. Bodies
use FLU: +X forward, +Y left, +Z up. Quaternions are [x, y, z, w], and rotate a body vector into the
site frame. A future C++ implementation must reproduce schemas/conformance/frame_vectors.json.
"""

import math

Vector = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]

UNREAL_CM_PER_M = 100.0
FRAME_NAME = "site_enu_rh_si"
_HALF_SQRT = math.sqrt(0.5)
_ENU_TO_NED: Quaternion = (_HALF_SQRT, _HALF_SQRT, 0.0, 0.0)
_FRD_TO_FLU: Quaternion = (1.0, 0.0, 0.0, 0.0)


def quat_multiply(a: Quaternion, b: Quaternion) -> Quaternion:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quat_conjugate(q: Quaternion) -> Quaternion:
    return (-q[0], -q[1], -q[2], q[3])


def quat_rotate(q: Quaternion, v: Vector) -> Vector:
    """Rotate a vector by the formula v' = q v q*. The algebra is the same in either handedness."""
    x, y, z, _ = quat_multiply(quat_multiply(q, (v[0], v[1], v[2], 0.0)), quat_conjugate(q))
    return (x, y, z)


def yaw_to_quat(yaw_rad: float) -> Quaternion:
    return (0.0, 0.0, math.sin(yaw_rad / 2.0), math.cos(yaw_rad / 2.0))


def quat_to_yaw(q: Quaternion) -> float:
    x, y, z, w = q
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


# Site (ENU, meters) to Unreal (left-handed: X forward, Y right, Z up, centimeters).
def site_to_unreal_position(position_m: Vector) -> Vector:
    """Also for velocities: m/s become cm/s. Unreal's +Y is the site's -Y."""
    x, y, z = position_m
    return (x * UNREAL_CM_PER_M, -y * UNREAL_CM_PER_M, z * UNREAL_CM_PER_M)


def unreal_to_site_position(position_cm: Vector) -> Vector:
    x, y, z = position_cm
    return (x / UNREAL_CM_PER_M, -y / UNREAL_CM_PER_M, z / UNREAL_CM_PER_M)


def site_to_unreal_quat(q: Quaternion) -> Quaternion:
    """A mirror across the XZ plane negates the X and Z parts. The conversion is its own inverse."""
    return (-q[0], q[1], -q[2], q[3])


def unreal_to_site_quat(q: Quaternion) -> Quaternion:
    return site_to_unreal_quat(q)


def site_to_unreal_angular_velocity(omega_radps: Vector) -> Vector:
    """Angular velocity is an axial vector: under a mirror it picks up an extra sign change."""
    return (-omega_radps[0], omega_radps[1], -omega_radps[2])


def site_yaw_rate_to_unreal(yaw_rate_radps: float) -> float:
    """Contract: positive turns left. Unreal: positive yaw turns right, seen from above."""
    return -yaw_rate_radps


def site_yaw_to_unreal_degrees(yaw_rad: float) -> float:
    """FRotator yaw in degrees. Note that FRotator uses degrees and the contract uses radians."""
    return -math.degrees(yaw_rad)


def unreal_yaw_degrees_to_site(yaw_deg: float) -> float:
    return -math.radians(yaw_deg)


# Site (ENU) to NED, which common robotics and aerospace tools use, with an FRD body.
def enu_to_ned_vector(v: Vector) -> Vector:
    """Swap east and north, and negate up. The same operation converts NED back to ENU."""
    return (v[1], v[0], -v[2])


def enu_to_ned_quat(q: Quaternion) -> Quaternion:
    """A body-FLU-to-ENU rotation, as a body-FRD-to-NED rotation."""
    return quat_multiply(quat_multiply(_ENU_TO_NED, q), quat_conjugate(_FRD_TO_FLU))


def ned_to_enu_quat(q: Quaternion) -> Quaternion:
    return quat_multiply(quat_multiply(quat_conjugate(_ENU_TO_NED), q), _FRD_TO_FLU)


def enu_yaw_to_ned_heading(yaw_rad: float) -> float:
    """ENU yaw is counterclockwise from east. NED heading is clockwise from north."""
    return (math.pi / 2.0 - yaw_rad) % (2.0 * math.pi)


def golden_vectors() -> dict[str, list[dict[str, object]]]:
    """Reference conversions, for tests here and for the future C++ implementation."""
    cases: dict[str, list[dict[str, object]]] = {"position": [], "yaw": [], "quaternion": []}
    for position in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (12.5, -3.25, 0.5)):
        cases["position"].append(
            {
                "site_m": list(position),
                "unreal_cm": list(site_to_unreal_position(position)),
                "ned_m": list(enu_to_ned_vector(position)),
            }
        )
    for degrees in (0.0, 30.0, 90.0, -90.0, 179.0):
        yaw = math.radians(degrees)
        cases["yaw"].append(
            {
                "site_yaw_rad": yaw,
                "unreal_yaw_deg": site_yaw_to_unreal_degrees(yaw),
                "ned_heading_rad": enu_yaw_to_ned_heading(yaw),
            }
        )
    half = math.sqrt(0.5)
    for q in (
        (0.0, 0.0, 0.0, 1.0),
        yaw_to_quat(math.radians(90.0)),
        (half, 0.0, 0.0, half),
        (0.0, half, 0.0, half),
        (0.1825742, 0.3651484, 0.5477226, 0.7302967),
    ):
        cases["quaternion"].append(
            {
                "site_xyzw": list(q),
                "unreal_xyzw": list(site_to_unreal_quat(q)),
                "ned_frd_xyzw": list(enu_to_ned_quat(q)),
            }
        )
    return cases
