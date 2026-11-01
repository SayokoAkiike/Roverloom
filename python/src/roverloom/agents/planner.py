"""A minimal explore-and-replan baseline.

The agent starts with an empty map and treats unknown ground as free, so it explores toward
the target and replans with A* whenever its range sensor reveals an obstacle on the path.
"""

import heapq
import math

from roverloom.agents.basic import next_target, steer_to
from roverloom.api import STOP, Action, MissionBrief, Observation

_CELL_M = 1.0
_LOOKAHEAD_CELLS = 4
_MAX_EXPANSIONS = 60_000
_NEIGHBORS = (
    (1, 0, 1.0),
    (-1, 0, 1.0),
    (0, 1, 1.0),
    (0, -1, 1.0),
    (1, 1, math.sqrt(2.0)),
    (1, -1, math.sqrt(2.0)),
    (-1, 1, math.sqrt(2.0)),
    (-1, -1, math.sqrt(2.0)),
)
Cell = tuple[int, int]


def _cell(x: float, y: float) -> Cell:
    return (math.floor(x / _CELL_M), math.floor(y / _CELL_M))


def _center(cell: Cell) -> tuple[float, float]:
    return ((cell[0] + 0.5) * _CELL_M, (cell[1] + 0.5) * _CELL_M)


class GridReplannerAgent:
    _STUCK_WINDOW_S = 12.0
    _BACKUP_S = 4.0

    def __init__(self) -> None:
        self._brief: MissionBrief | None = None

    def reset(self, brief: MissionBrief, seed: int) -> None:
        self._brief = brief
        self._blocked: set[Cell] = set()
        self._path: list[Cell] = []
        self._target_index = -1
        self._inflate = math.ceil((brief.body_radius_m + 0.8) / _CELL_M)
        self._min_cell = _cell(*brief.extent_min_xy)
        self._max_cell = _cell(*brief.extent_max_xy)
        self._check_time = 0.0
        self._check_xy = (brief.start_pose.x_m, brief.start_pose.y_m)
        self._backup_until = -1.0

    def _mark(self, x: float, y: float) -> bool:
        changed = False
        cx, cy = _cell(x, y)
        reach = self._inflate
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                if dx * dx + dy * dy <= reach * reach:
                    cell = (cx + dx, cy + dy)
                    if cell not in self._blocked:
                        self._blocked.add(cell)
                        changed = True
        return changed

    def _plan(self, start: Cell, goal: Cell) -> list[Cell]:
        """A* over the known map. Returns an empty list when no path is found."""
        frontier: list[tuple[float, int, Cell]] = [(0.0, 0, start)]
        came_from: dict[Cell, Cell] = {}
        cost = {start: 0.0}
        order = 0
        expansions = 0
        while frontier and expansions < _MAX_EXPANSIONS:
            _, _, current = heapq.heappop(frontier)
            expansions += 1
            if current == goal:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path
            for dx, dy, step in _NEIGHBORS:
                near = (current[0] + dx, current[1] + dy)
                if near in self._blocked or not self._within(near):
                    continue
                new_cost = cost[current] + step
                if new_cost < cost.get(near, math.inf):
                    cost[near] = new_cost
                    came_from[near] = current
                    order += 1
                    remaining = math.hypot(goal[0] - near[0], goal[1] - near[1])
                    heapq.heappush(frontier, (new_cost + remaining, order, near))
        return []

    def _within(self, cell: Cell) -> bool:
        return (
            self._min_cell[0] < cell[0] < self._max_cell[0]
            and self._min_cell[1] < cell[1] < self._max_cell[1]
        )

    def act(self, observation: Observation) -> Action:
        brief = self._brief
        assert brief is not None
        target = next_target(brief, observation)
        if target is None:
            return STOP
        pose = observation.estimated_pose
        now = observation.time_s

        changed = False
        for reading in observation.range_scan:
            if reading.range_m is not None:
                angle = pose.yaw_rad + reading.bearing_rad
                changed |= self._mark(
                    pose.x_m + reading.range_m * math.cos(angle),
                    pose.y_m + reading.range_m * math.sin(angle),
                )

        if now < self._backup_until:
            # Measure progress afresh after backing up, or reversing would look like being stuck.
            self._check_time = now
            self._check_xy = (pose.x_m, pose.y_m)
            return Action(-0.5 * brief.max_speed_mps, 0.0)

        # No progress means something unseen is in the way: remember it and back out.
        if now - self._check_time >= self._STUCK_WINDOW_S:
            moved = math.hypot(pose.x_m - self._check_xy[0], pose.y_m - self._check_xy[1])
            if moved < 0.8:
                self._mark(
                    pose.x_m + (brief.body_radius_m + 0.8) * math.cos(pose.yaw_rad),
                    pose.y_m + (brief.body_radius_m + 0.8) * math.sin(pose.yaw_rad),
                )
                self._backup_until = now + self._BACKUP_S
                changed = True
            self._check_time = now
            self._check_xy = (pose.x_m, pose.y_m)

        start = _cell(pose.x_m, pose.y_m)
        goal = _cell(target.x_m, target.y_m)
        self._blocked.discard(start)
        self._blocked.discard(goal)
        if observation.targets_reached != self._target_index:
            self._target_index = observation.targets_reached
            changed = True
        if start in self._path:
            del self._path[: self._path.index(start)]
        elif self._path:
            changed = True
        if changed or not self._path or any(c in self._blocked for c in self._path):
            self._path = self._plan(start, goal)
        if not self._path:
            # The map says the target is unreachable. Forget it and explore again.
            self._blocked.clear()
            return STOP
        waypoint = self._path[min(_LOOKAHEAD_CELLS, len(self._path) - 1)]
        if waypoint == goal:
            return steer_to(brief, observation, target.x_m, target.y_m)
        return steer_to(brief, observation, *_center(waypoint))
