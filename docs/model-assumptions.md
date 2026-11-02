# Model assumptions

**Nothing here has been validated against a real rover, soil test, or mission.** Numbers were chosen so
that choices have clear trade-offs. Do not cite results from this project as predictions about real
vehicles. To replace a value, cite a source, and increase the matching version.

| Model | Simplification | Values with no empirical basis | Main consequence |
| --- | --- | --- | --- |
| Motion | Kinematic 2.5D; no wheel-soil contact, tipping, or suspension | Acceleration limits; slip formula | Rough ground only slows the rover |
| Slip | `soil + factor * slope + noise` | Factor 0.5; scale by ground pressure | Not terramechanics. See [lightweight models](lightweight-models.md) |
| Rover Builder | Algebra over part sizes | All mass, cost, volume, and power coefficients | Trade-offs are designed, not discovered |
| Design classes | Three budget tiers | Limits of 40, 70, and 100 | Set where the three standard rovers fall |
| Compatibility rules | Fixed thresholds | Arm 250 kg, RTG 400 kg, beams per compute tier | Plausibility only |
| Battery | Energy store with a peak limit | Discharge of 2 per hour; no temperature or aging | Can be run down, but never damaged |
| Solar | Constant scale | `solar_factor`; no day, night, or angle | Long missions are not modeled honestly |
| RTG | Constant output | Mass and cost per watt | Not based on any real unit |
| Sensors | Gaussian noise, ray casts on circles | All noise levels | No vision, no occlusion by terrain |
| Inspection | True value plus noise | All values, and the share of 30% to 70% | Game points, not science return |
| Comms | Fixed delay, independent loss | All rates | No bandwidth limit, or real orbital passes |
| Faults | Scheduled, or a Poisson process | **All rates and severities are invented** | Labels: `mars_inspired` describes a type, and never a measured rate |

## What results can and cannot support

Supported: "On scenario X in this model, planner A sent more value than planner B, over these seeds."

Not supported: anything about real rovers, or a claim that a method is novel or better in general. Mission
planning, re-observation, and replanning have a long literature, which this project has not surveyed.
The adaptive planner is a baseline for this benchmark, not a research result.

## Scenario and agent coupling

The adaptive planner was developed while looking at the benchmark's scenarios, with corrections made
after seeing results, and the design missions were adjusted until the standard rovers differed. Results
therefore show that the benchmark can tell these behaviors apart. They are not a held-out evaluation.
Neither scenarios nor seeds were held out, as [the record of their use](scientific-benchmark.md#how-scenarios-and-seeds-were-used)
shows. A real competition needs scenarios that no entrant has seen.
