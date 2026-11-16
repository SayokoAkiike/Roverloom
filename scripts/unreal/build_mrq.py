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

import os
import sys

import unreal  # type: ignore[import-not-found]

tools = unreal.AssetToolsHelpers.get_asset_tools()
FOLDER = "/Game/Licensed/Gale/MRQ"
FPS = 30


def make_sequence(name: str, seconds: float, keys: list) -> "unreal.LevelSequence":
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
    component = camera.get_object_template().get_component_by_class(unreal.CameraComponent)
    if component is not None:
        component.set_editor_property("field_of_view", 62.0)
        unreal.log("MRQ_CAMERA field of view set")
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
    # The video: the camera drifts from the left of the rover to behind and to the left of it, as the rover drives away (+X)
    video = [
        (0, (450, -380, 110), (0, -3, 140)),
        (450, (150, -520, 120), (0, -4, 108)),
        (900, (-300, -520, 130), (0, -5, 72)),
    ]
    make_sequence("Seq_GaleVideo", 30.0, video)
    saved = unreal.Paths.project_saved_dir()
    make_config("Cfg_Still", os.path.join(saved, "MovieRenders/Still"), 48)
    make_config("Cfg_Video", os.path.join(saved, "MovieRenders/Video"), 48)
    unreal.log("MRQ_ASSETS_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
