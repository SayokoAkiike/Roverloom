#!/bin/zsh
# Render a Movie Render Queue job of the Gale level from the command line, in the Capture profile.
#
#   scripts/unreal/render_mrq.sh still noon        # Seq_GaleStill with Cfg_Still, light preset noon
#   scripts/unreal/render_mrq.sh close noon        # Seq_RoverClose: a close view of the rover, for its materials
#   scripts/unreal/render_mrq.sh video afternoon   # Seq_GaleVideo with Cfg_Video, the rover driving
#
# Needs the assets of build_mrq.py, the Gale level, and the engine at $UE_ROOT (default ~/UnrealEngineInstall/UE_5.8). Frames go to
# unreal/Saved/MovieRenders/<Still|Video>/, which Git ignores. The editor is closed by asking it to quit, never by a signal.
set -u
kind=${1:?still, close, top, or video}
preset=${2:?noon, afternoon, or sunset}
shift 2
UE_ROOT=${UE_ROOT:-$HOME/UnrealEngineInstall/UE_5.8}
repo=${0:A:h:h:h}
project="$repo/unreal/Roverloom.uproject"
case $kind in
  still) seq=/Game/Licensed/Gale/MRQ/Seq_GaleStill cfg=/Game/Licensed/Gale/MRQ/Cfg_Still out=Still extra=() ;;
  close) seq=/Game/Licensed/Gale/MRQ/Seq_RoverClose cfg=/Game/Licensed/Gale/MRQ/Cfg_Still out=Still extra=() ;;
  top) seq=/Game/Licensed/Gale/MRQ/Seq_RoverTop cfg=/Game/Licensed/Gale/MRQ/Cfg_Still out=Still extra=() ;;
  video) seq=/Game/Licensed/Gale/MRQ/Seq_GaleVideo cfg=/Game/Licensed/Gale/MRQ/Cfg_Video out=Video extra=(-RoverDrive=f1-flat) ;;
  *) echo "still, close, top, or video"; exit 2 ;;
esac
log=${MRQ_LOG:-${TMPDIR:-/tmp}/mrq_${kind}_${preset}.log}
"$UE_ROOT/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" "$project" \
  "/Game/Licensed/Gale/Gale?game=/Script/Roverloom.RoverPlaygroundGameMode" -game -windowed -ResX=1280 -ResY=720 \
  -LevelSequence=$seq -MoviePipelineConfig=$cfg \
  -MoviePipelineLocalExecutorClass=/Script/MovieRenderPipelineCore.MoviePipelineInProcessExecutor \
  -RoverLight=$preset -RoverProfile=capture -NoLoadingScreen -abslog="$log" $extra "$@" >/dev/null 2>&1 &
pid=$!
for i in $(seq 1 ${MRQ_WAIT:-3600}); do
  kill -0 $pid 2>/dev/null || break
  grep -q 'MoviePipelineLinearExecutorBase finished' "$log" 2>/dev/null && break
  sleep 2
done
sleep 3
kill -0 $pid 2>/dev/null && osascript -e 'tell application "UnrealEditor" to quit' >/dev/null 2>&1
for i in $(seq 1 30); do kill -0 $pid 2>/dev/null || break; sleep 1; done
grep -E 'Movie Pipeline completed|MoviePipelineLinearExecutorBase finished' "$log" | sed 's/.*LogMovieRenderPipeline: //'
ls "$repo/unreal/Saved/MovieRenders/$out" | wc -l | sed 's/^ *//; s/$/ files in Saved\/MovieRenders\/'"$out"'/'
