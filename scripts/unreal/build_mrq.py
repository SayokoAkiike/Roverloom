"""Build the Movie Render Queue assets for the Gale stills and video: two level sequences and two pipeline configs.
Unreal Editor Python.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_mrq.py" -unattended -nullrhi

Output: /Game/Licensed/Gale/MRQ/, which Git ignores. Needs the MovieRenderPipeline and SequencerScripting plugins (the project file lists them).

  Seq_GaleStill  one second, a fixed camera 4.5 m ahead of the start and a little to its left, looking back at the rover
  Seq_GaleVideo  30 seconds, the same camera drifting slowly sideways while the rover drives (-RoverDrive=f1-flat)
  Cfg_Still      1920 x 1080 PNG, with warm-up frames so that Lumen and the rover settle
  Cfg_Video      1920 x 1080 PNG frames at 30 fps, to be joined into a video outside Git

The light preset and the render profile come from the game's command line (-RoverLight, -RoverProfile=capture), so one sequence
serves all three presets. See scripts/unreal/render_mrq.sh for the command.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import math
import os
import sys

import unreal  # type: ignore[import-not-found]

tools = unreal.AssetToolsHelpers.get_asset_tools()
FOLDER = "/Game/Licensed/Gale/MRQ"
FPS = 30


def make_sequence(
    name: str, seconds: float, keys: list, field_of_view: float = 90.0
) -> "unreal.LevelSequence":
    """keys: (frame, (x, y, z), (roll, pitch, yaw)) for the camera, in Unreal cm and degrees."""
    path = f"{FOLDER}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        sequence = unreal.EditorAssetLibrary.load_asset(path)
        for binding in list(sequence.get_bindings()):
            binding.remove()
        for track in list(sequence.get_tracks()):
            sequence.remove_track(track)
    else:
        sequence = tools.create_asset(
            name, FOLDER, unreal.LevelSequence, unreal.LevelSequenceFactoryNew()
        )
    frames = int(seconds * FPS)
    sequence.set_display_rate(unreal.FrameRate(FPS, 1))
    sequence.set_playback_start(0)
    sequence.set_playback_end(frames)

    # A plain camera, not a CineCamera: it exposes and focuses as the game's own camera does (a CineCamera's physical f/2.8 blurs the
    # rover and its exposure needs another scale). 62 degrees of field of view.
    camera = sequence.add_spawnable_from_class(unreal.CameraActor)
    template = camera.get_object_template()
    component = template.get_editor_property("camera_component")
    if component is not None:
        component.set_editor_property("field_of_view", field_of_view)
        unreal.log(f"MRQ_CAMERA {name}: field of view {field_of_view}")
    track = camera.add_track(unreal.MovieScene3DTransformTrack)
    section = track.add_section()
    section.set_range(0, frames)
    channels = (
        section.get_all_channels()
    )  # Location X Y Z, Rotation X Y Z (roll, pitch, yaw), Scale X Y Z
    for frame, location, rotation in keys:
        for index, value in enumerate(location):
            channels[index].add_key(unreal.FrameNumber(frame), float(value))
        for index, value in enumerate(rotation):
            channels[3 + index].add_key(unreal.FrameNumber(frame), float(value))
    for index in (6, 7, 8):
        channels[index].set_default(1.0)

    cut_track = sequence.add_track(unreal.MovieSceneCameraCutTrack)
    cut = cut_track.add_section()
    cut.set_range(0, frames)
    cut.set_camera_binding_id(unreal.MovieSceneSequenceExtensions.get_binding_id(sequence, camera))
    unreal.EditorAssetLibrary.save_loaded_asset(sequence)
    return sequence


def look_at(position, target, yaw_offset=0.0):
    """(roll, pitch, yaw) in degrees for a camera at position looking at target, turned by yaw_offset (positive turns it right)."""
    dx, dy, dz = (target[i] - position[i] for i in range(3))
    return (
        0.0,
        math.degrees(math.atan2(dz, math.hypot(dx, dy))),
        math.degrees(math.atan2(dy, dx)) + yaw_offset,
    )


def make_cuts_sequence(name: str, seconds: float, cuts: list) -> "unreal.LevelSequence":
    """Several cameras with a hard cut between them. cuts: (first frame, last frame, keys, field of view); keys as in make_sequence."""
    path = f"{FOLDER}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        sequence = unreal.EditorAssetLibrary.load_asset(path)
        for binding in list(sequence.get_bindings()):
            binding.remove()
        for track in list(sequence.get_tracks()):
            sequence.remove_track(track)
    else:
        sequence = tools.create_asset(
            name, FOLDER, unreal.LevelSequence, unreal.LevelSequenceFactoryNew()
        )
    frames = int(seconds * FPS)
    sequence.set_display_rate(unreal.FrameRate(FPS, 1))
    sequence.set_playback_start(0)
    sequence.set_playback_end(frames)
    cut_track = sequence.add_track(unreal.MovieSceneCameraCutTrack)
    for cut_spec in cuts:
        first, last, keys, field_of_view = cut_spec[:4]
        cine = cut_spec[4] if len(cut_spec) > 4 else None
        camera = sequence.add_spawnable_from_class(
            unreal.CineCameraActor if cine else unreal.CameraActor
        )
        component = camera.get_object_template().get_editor_property("camera_component")
        if cine:
            # A real lens: a shallow depth of field, focused on a set distance (cm)
            component.set_editor_property("current_focal_length", cine["focal_mm"])
            component.set_editor_property("current_aperture", cine["aperture"])
            focus = component.get_editor_property("focus_settings")
            focus.focus_method = unreal.CameraFocusMethod.MANUAL
            focus.manual_focus_distance = cine["focus_cm"]
            component.set_editor_property("focus_settings", focus)
        else:
            component.set_editor_property("field_of_view", field_of_view)
        section = camera.add_track(unreal.MovieScene3DTransformTrack).add_section()
        section.set_range(first, last)
        channels = section.get_all_channels()
        for frame, location, rotation in keys:
            for index, value in enumerate(location):
                channels[index].add_key(unreal.FrameNumber(frame), float(value))
            for index, value in enumerate(rotation):
                channels[3 + index].add_key(unreal.FrameNumber(frame), float(value))
        for index in (6, 7, 8):
            channels[index].set_default(1.0)
        cut = cut_track.add_section()
        cut.set_range(first, last)
        cut.set_camera_binding_id(
            unreal.MovieSceneSequenceExtensions.get_binding_id(sequence, camera)
        )
    unreal.EditorAssetLibrary.save_loaded_asset(sequence)
    return sequence


def make_config(name: str, output_dir: str, warm_up: int) -> None:
    path = f"{FOLDER}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        config = unreal.EditorAssetLibrary.load_asset(path)
    else:
        config = tools.create_asset(
            name,
            FOLDER,
            unreal.MoviePipelinePrimaryConfig,
            unreal.MoviePipelinePrimaryConfigFactory(),
        )
    output = config.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
    output.output_resolution = unreal.IntPoint(1920, 1080)
    output.output_directory = unreal.DirectoryPath(output_dir)
    output.file_name_format = "gale.{frame_number}"  # No {sequence_name}: it is empty here, and the name would start with a dot
    output.use_custom_frame_rate = True
    output.output_frame_rate = unreal.FrameRate(FPS, 1)
    # The ordinary "Deferred Rendering" pass. (DeferredPass_DetailLighting is a lighting-only view: grey, without the textures.)
    stale = config.find_setting_by_class(unreal.MoviePipelineDeferredPass_DetailLighting)
    if stale is not None:
        config.remove_setting(stale)
    config.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
    # MRQ loads the map with its own game mode, which would leave out the rover, the lights, the rocks, and the dust. Name ours.
    override = config.find_or_add_setting_by_class(unreal.MoviePipelineGameOverrideSetting)
    override.game_mode_override = unreal.load_class(
        None, "/Script/Roverloom.RoverPlaygroundGameMode"
    )
    config.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
    anti_aliasing = config.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
    anti_aliasing.engine_warm_up_count = warm_up
    anti_aliasing.render_warm_up_count = warm_up
    anti_aliasing.override_anti_aliasing = True
    anti_aliasing.anti_aliasing_method = unreal.AntiAliasingMethod.AAM_TSR
    anti_aliasing.spatial_sample_count = 1
    anti_aliasing.temporal_sample_count = 1
    saved = unreal.EditorAssetLibrary.save_loaded_asset(config)
    unreal.log(f"MRQ_CONFIG {name}: saved={saved}")


def main() -> int:
    # The rover starts at the origin facing +X. Unreal +Y is to its right. A camera ahead and to the left, looking back at it.
    # Looking from (450, -380, 110) to (0, 0, 80): the yaw points from the camera toward the rover.
    still = [(0, (450, -380, 110), (0, -3, 140))]
    make_sequence("Seq_GaleStill", 1.0, still)
    # A close three-quarter view of the rover, for judging its materials: 2.9 m from it, a little above the wheels
    make_sequence("Seq_RoverClose", 1.0, [(0, (230, -170, 75), (0, -2, 143.5))])
    # The sky toward the sun, for tuning the sunset: the camera 2 m up, looking 6 degrees above the horizon at azimuth 15 (where the sunset
    # preset puts the sun), at the plain camera's 90 degrees of field of view
    make_sequence("Seq_Sky", 1.0, [(0, (0, 0, 200), (0, 6, 15))])
    # Toward Aeolis Mons (Mount Sharp): 33 km away at 14.8 degrees north of east, which is -14.8 in Unreal yaw (+Y is south). Looking 3 degrees
    # up, at 90 degrees of field of view, from 2 m up
    make_sequence("Seq_Mountain", 1.0, [(0, (0, 0, 200), (0, 3, -14.8))])
    # A fixed side view for measuring when the drive script starts, in sequence frames (the warm-up frames use up game time first)
    side = (200, -650, 100)
    make_sequence("Seq_Probe", 8.0, [(0, side, look_at(side, (200, 0, 80)))], 62.0)
    # From above and behind, to see the solar deck and the dust that settles on up-facing faces
    make_sequence("Seq_RoverTop", 1.0, [(0, (-330, -170, 330), (0, -38, 27))])
    # The drive script (-RoverDrive=f1-flat) in sequence frames, measured with Seq_Probe: the rover starts rolling at frame 42 at 0.5 m/s east
    # (1.667 cm a frame), stops at 282, spins in place from 402 to 642, and arcs from 762. It stays within 2 m of x = 400.
    start, stop = 42, 282

    def rover_x(frame):
        return 1.667 * (min(max(frame, start), stop) - start)

    # Three compositions, each with the rover at rest (frame 29 of a 1 s sequence), or rolling for the close-up
    wide = (330, -300, 45)  # (a) low, from the front left, wide
    make_sequence("Seq_CompA", 1.0, [(0, wide, look_at(wide, (0, 0, 90)))], 100.0)
    behind = (
        -700,
        30,
        150,
    )  # (b) from behind and a little to the right of the rover, toward Mount Sharp (14.8 degrees north of east)
    make_sequence("Seq_CompB", 1.0, [(0, behind, (0, 1.5, -12))], 50.0)
    # (c) a close view of the front-left wheel and its dust, a shallow depth of field, following the rover; the wheel is 205 cm away
    c_keys = []
    for frame in (0, 42, 180):
        wheel = (97.6 + rover_x(frame), -103.7, 25)
        position = (wheel[0] + 110, wheel[1] - 170, 40)
        c_keys.append(
            (frame, position, look_at(position, wheel, 6.0))
        )  # Turned 6 degrees right, so that the wheel sits left of centre
    make_cuts_sequence(
        "Seq_CompC",
        6.0,
        [(0, 180, c_keys, 40.0, {"focal_mm": 50.0, "aperture": 2.0, "focus_cm": 205.0})],
    )

    # A view from behind the rolling rover, toward the sun at sunset, for the dust that the sun lights from behind (frame 150 of 180)
    dust_cam = (-520, 60, 90)
    make_sequence("Seq_DustTest", 6.0, [(0, dust_cam, (0, 2, -8))], 62.0)

    # The video, three cuts of ten seconds. The rover sits on a third of the frame in each: the camera is turned a few degrees past it
    # (positive yaw turns the camera right, which puts the rover on the left third)
    offset = (-380, -250, 110)
    follow = []
    for frame in (0, 42, 282, 300):
        target = (rover_x(frame), 0, 80)
        position = (target[0] + offset[0], target[1] + offset[1], offset[2])
        follow.append((frame, position, look_at(position, target, 9.0)))
    centre = (400, 0, 90)
    orbit = []
    for i, frame in enumerate(range(300, 601, 50)):
        angle = math.radians(-150 + i * 20)  # Sweeps 120 degrees around the spinning rover
        position = (centre[0] + 520 * math.cos(angle), centre[1] + 520 * math.sin(angle), 130)
        orbit.append((frame, position, look_at(position, centre, -9.0)))
    push = []
    for frame, distance in ((600, 1.0), (900, 0.7)):
        position = (400 - 330 * distance, 260 * distance, 45)
        push.append((frame, position, look_at(position, (400, 0, 60), 10.0)))
    make_cuts_sequence(
        "Seq_GaleVideo",
        30.0,
        [(0, 299, follow, 62.0), (300, 599, orbit, 55.0), (600, 900, push, 70.0)],
    )
    saved = unreal.Paths.project_saved_dir()
    make_config("Cfg_Still", os.path.join(saved, "MovieRenders/Still"), 48)
    make_config("Cfg_Video", os.path.join(saved, "MovieRenders/Video"), 48)
    unreal.log("MRQ_ASSETS_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
