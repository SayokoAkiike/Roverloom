# G4a: the G3 mission played through the keyboard path, 2026-11-08

**Status: passed. The owner drove the rover to the target by keyboard and the Mission Core judged success on the HUD
(run `g4a-human-1`); a simulated-keyboard run (`g4a-2`) passed before it. Merge waits for CI on
`feature/unreal-project` to be confirmed green.**

## Change

- `play-g3`: opens G3's mission link for a person at the keyboard. The dispatcher runs `play-` presets windowed on
  rdnight's session and does not wait for owner idle (the owner is the player); an owner Unreal process, memory, and
  Microsoft processes still refuse.
- `keys-g3`: the same, with W held through Enhanced Input (`InjectInputForAction` on the player's Drive action) from
  6 s to 26 s after the rig is ready. The drive script is not used; the command reaches the rover through
  `OnDrive` -> keyboard source -> `CommandRouter`, as a real key does.
- The first verdict from the Mission Core is captured as `Mission.png`. Mission Core rules, scoring, and the physics
  model are unchanged; Unreal still only shows the verdict.

## Evidence (run `g4a-2`)

| Item | Value |
| --- | --- |
| Machine, OS user | Mac mini (`hostname -s` of the owner's Mac mini), `rdnight` |
| Unreal process | PID 91844, started 2026-11-08 01:43:18 JST; log 01:43:19.786 to 01:44:18.114 JST (exited after the 45 s bench) |
| Command | `UnrealEditor Roverloom.uproject /Engine/Maps/Entry?game=...RoverPlaygroundGameMode -game -RenderOffscreen -ResX=1600 -ResY=900 -RoverBench=45 -RoverDrive=keys-g3`, sandboxed (`night.sb`) |
| Durations | build 11 s, automation tests 21 s, game 61 s wall (dispatcher call) |
| Key input | `simulated key W down at 6.01 s`, `up at 26.01 s`; HUD shows `Input keyboard`, `Watchdog ok` |
| Mission Core | `mission_started` 0.0 s, `target_reached` 18.2 s, `mission_ended` `success` 18.2 s |
| HUD | `Mission (Python): g3_reach_target targets 1/1 SUCCESS t 18.2 s` at x 6.07 m (`mission-success.png`) |
| Tests | automation 5 of 5; dispatcher tests 8 passed |

A first build failed (`InjectInputForAction` takes four arguments in UE 5.8); fixed in one retry.

## Run by a person (`g4a-human-1`)

The owner, on the Mac mini through Screen Sharing switched to `rdnight`'s session, drove with the keyboard.

| Item | Value |
| --- | --- |
| Machine, OS user | Mac mini, `rdnight` (game window on `rdnight`'s graphical session) |
| Unreal process | PID 91808, started 2026-11-08 02:24:03 JST; log 02:24:17 to 02:26:21 JST; exited after the 120 s session |
| Command | `... -game -windowed -ResX=1600 -ResY=900 -RoverBench=120 -RoverDrive=play-g3`, sandboxed (`night.sb`) |
| Input | No simulated key lines in the log (0); window focus 0% for the first 40 s, then 70-100% after the owner clicked it |
| Mission Core | `mission_started` 0.0 s, `target_reached` 57.1 s, `mission_ended` `success` 57.1 s |
| HUD | `Mission (Python): g3_reach_target targets 1/1 SUCCESS t 57.1 s`, `Input keyboard`, `Watchdog ok`, speed +0.50 m/s, x 6.06 m (`human-mission-success.png`) |
| Rendering | windowed, display-synced: 60.0 fps, GPU 14.3-15.1 ms (offscreen runs are uncapped, about 85 fps) |
| Duration | 140 s wall for the dispatcher call |
| Mac mini preflight | no lock, no forbidden processes, no owner Unreal, 72% memory free |
