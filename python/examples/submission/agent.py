"""An example competition submission: runs the public mission planner through the SDK."""

from roverloom.agents.sdk import MissionPlanner, SkillAgent


class Agent(SkillAgent):
    def make_planner(self, brief, seed):
        return MissionPlanner(brief)
