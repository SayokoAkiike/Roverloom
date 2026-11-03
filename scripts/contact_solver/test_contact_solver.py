"""Unit tests for the contact solver research code. Run from the repository root:

python -m unittest discover -s scripts -p "test_contact_solver.py" -t scripts
"""

from __future__ import annotations

import math
import random
import unittest
from typing import Any

from contact_solver.methods import block_gauss_seidel, fista, primal_active_set
from contact_solver.problem import build, evaluate, project

MASS, GRAVITY = 853.5, 371.0


def six_wheel(
    yaw_rate_degps: float = 0.0,
    turn_command_degps: float = 0.0,
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0),
    mode: int = 0,
    friction: float = 0.6,
    hit: tuple[bool, ...] = (True,) * 6,
) -> dict[str, Any]:
    """A dump-shaped input: pathfinder_6w's box on flat ground, wheels at static compression."""
    ix = MASS / 12 * (150**2 + 40**2)
    iy = MASS / 12 * (200**2 + 40**2)
    iz = MASS / 12 * (200**2 + 150**2)
    rim = math.radians(turn_command_degps) * 103.7
    wheels = []
    for y in (-103.7, 103.7):
        for x in (97.6, 0.0, -97.6):
            spin = (rim if y < 0 else -rim) / 25
            wheels.append(
                {
                    "hit": hit[len(wheels)],
                    "comp": 5.0,
                    "comp_rate": 0.0,
                    "point": [x, y, -45.0],
                    "normal": [0.0, 0.0, 1.0],
                    "forward": [1.0, 0.0, 0.0],
                    "lateral": [0.0, 1.0, 0.0],
                    "mode": mode,
                    "target": spin,
                    "spin": spin,
                }
            )
    return {
        "dt": 1 / 60,
        "params": {
            "radius": 25.0,
            "inertia": 3750.0,
            "spring": MASS * GRAVITY / 6 / 5,
            "damper": 0.0,
            "friction": friction,
            "motor": 6e5,
            "brake": 2e6,
        },
        "body": {
            "inv_mass": 1 / MASS,
            "inv_inertia": [[1 / ix, 0, 0], [0, 1 / iy, 0], [0, 0, 1 / iz]],
            "com": [0.0, 0.0, 0.0],
            "v": list(velocity),
            "w": [0.0, 0.0, math.radians(yaw_rate_degps)],
            "acc": [0.0, 0.0, -GRAVITY],
            "ext": [0.0, 0.0, 0.0],
        },
        "wheels": wheels,
    }


def distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


class FormulationTest(unittest.TestCase):
    def test_dual_matrix_matches_the_wheel_model(self) -> None:
        problem = build(six_wheel(yaw_rate_degps=10.0, turn_command_degps=28.178))
        a, b = problem.dual()
        dt, r, iw = problem.dt, problem.radius, problem.wheel_inertia
        # Longitudinal row of wheel 0 against itself: dt (1/M + arm.I^-1.arm + R^2/I_w).
        arm = problem.arms[0][0]
        body = 1 / MASS + sum(
            arm[k] * sum(problem.inv_inertia[k][j] * arm[j] for j in range(3)) for k in range(3)
        )
        self.assertAlmostEqual(a[0][0], dt * (body + r * r / iw), places=12)
        self.assertAlmostEqual(a[0][2], -dt * r / iw, places=12)
        self.assertAlmostEqual(a[2][2], dt / iw, places=12)
        self.assertEqual(a, [list(row) for row in zip(*a, strict=True)])
        # Rolling at the target: no slip and no spin error before any force.
        self.assertAlmostEqual(b[2], 0.0, places=12)

    def test_energy_identity_holds_for_any_feasible_x(self) -> None:
        problem = build(
            six_wheel(yaw_rate_degps=5.0, turn_command_degps=28.178, velocity=(10.0, -3.0, 0.0))
        )
        rng = random.Random(4)
        for _ in range(20):
            x = project([rng.uniform(-5e4, 5e4) for _ in range(18)], problem)
            result = evaluate(problem, x)
            scale = abs(result["kinetic_change"]) + problem.dt * abs(result["motor_power"]) + 1.0
            self.assertLess(abs(result["energy_identity_error"]) / scale, 1e-9)


class MethodTest(unittest.TestCase):
    def test_methods_agree_on_motion_in_a_turn(self) -> None:
        problem = build(six_wheel(yaw_rate_degps=18.98, turn_command_degps=28.178))
        reference = evaluate(problem, primal_active_set(problem)["x"])
        for result in (
            fista(problem, iterations=50000, tolerance=1e-10),
            block_gauss_seidel(problem, order="alternate", stop_natural=1e-10, passes=2000),
        ):
            got = evaluate(problem, result["x"])
            self.assertLess(result["natural"], 1e-8)
            self.assertLess(distance(got["velocity"], reference["velocity"]), 1e-6)
            self.assertLess(distance(got["angular_velocity"], reference["angular_velocity"]), 1e-9)
            self.assertLess(distance(got["net_force"], reference["net_force"]), 1e-2)

    def test_primal_active_set_reaches_optimality(self) -> None:
        for data in (
            six_wheel(yaw_rate_degps=18.98, turn_command_degps=28.178),
            six_wheel(velocity=(30.0, 40.0, 0.0), mode=1, friction=0.3),
            six_wheel(velocity=(20.0, 0.0, 0.0), mode=2),
        ):
            problem = build(data)
            result = primal_active_set(problem)
            checks = evaluate(problem, result["x"])
            self.assertLess(result["natural"], 1e-12)
            # A sliding force lies exactly on its circle, up to rounding.
            self.assertLessEqual(checks["circle_excess"], 1e-12)
            self.assertLessEqual(checks["torque_excess"], 1e-12)
            self.assertLessEqual(checks["friction_power"], 1e-6)

    def test_sliding_force_opposes_slip(self) -> None:
        problem = build(six_wheel(velocity=(30.0, 40.0, 0.0), mode=1, friction=0.3))
        for x in (primal_active_set(problem)["x"], fista(problem, tolerance=1e-10)["x"]):
            self.assertLess(evaluate(problem, x)["slide_angle_deg"], 1e-3)
        self.assertLess(evaluate(problem, primal_active_set(problem)["x"])["slide_angle_deg"], 1e-9)

    def test_warm_start_ignores_wheels_out_of_contact(self) -> None:
        problem = build(six_wheel(hit=(True, True, True, True, True, False)))
        start = [5e4] * 18
        result = block_gauss_seidel(problem, start=start)
        self.assertEqual(result["x"][15:17], [0.0, 0.0])
        self.assertLessEqual(evaluate(problem, result["x"])["circle_excess"], 0.0)

    def test_regularization_vanishes_as_gamma_falls(self) -> None:
        problem = build(six_wheel(yaw_rate_degps=18.98, turn_command_degps=28.178))
        reference = evaluate(problem, primal_active_set(problem)["x"])
        gaps = []
        for gamma in (1e-2, 1e-4, 1e-6):
            result = block_gauss_seidel(
                problem, order="alternate", gamma=gamma, passes=5000, tolerance=1e-12
            )
            gaps.append(
                distance(
                    evaluate(problem, result["x"])["angular_velocity"],
                    reference["angular_velocity"],
                )
            )
        self.assertGreater(gaps[0], gaps[1])
        self.assertGreater(gaps[1], gaps[2])


if __name__ == "__main__":
    unittest.main()
