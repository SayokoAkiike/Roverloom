# 0017: Keep experimental rally rules separate from benchmark scoring

Status: Accepted for the source prototype; Unreal build and playtest pending.

The owner requested a short rover game with route choices, supply stops, boosts, ghosts and customization. Add an opt-in `--rally` launcher and independent `rally-0.1` ruleset / `rally-drive-0.1` game model. Do not change pinned scientific scenarios, scoring or rover design compilation.

The garage accepts enumerated data, not executable code or arbitrary stats. Events depend on seed and global time slots. Primitive-based Unreal visuals avoid redistributing external assets. The existing six-wheel physics remains provisional. Python and TCP tests establish game-rule behavior only; they cannot establish rendering, native compilation or handling quality.

Consequences: rally times are local game results, not league scores. Component stats are game modifiers. Engine validation remains a release gate for calling the new 3D mode playable. CaP rally control and free-form mesh assembly need subsequent design and tests.
