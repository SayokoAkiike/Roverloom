"""List the Movie Render Queue and Level Sequence classes Editor Python can see, to plan a still and video render. Read-only."""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import unreal  # type: ignore[import-not-found]

WORDS = (
    "MoviePipeline",
    "LevelSequence",
    "MovieSceneCameraCutTrack",
    "MovieScene3DTransformTrack",
    "CineCameraActor",
)
names = [n for n in dir(unreal) if any(w in n for w in WORDS)]
print("PROBE count", len(names))
print(
    "PROBE",
    [
        n
        for n in names
        if n.startswith(
            (
                "MoviePipelinePrimary",
                "MoviePipelineQueue",
                "MoviePipelineOutputSetting",
                "MoviePipelineDeferred",
                "MoviePipelineImageSequenceOutput",
                "MoviePipelineMP4",
                "MoviePipelineEditorLibrary",
                "MoviePipelineAntiAlias",
                "MoviePipelineConsoleVariable",
                "MoviePipelineGameOverride",
                "LevelSequence",
            )
        )
    ][:60],
)
