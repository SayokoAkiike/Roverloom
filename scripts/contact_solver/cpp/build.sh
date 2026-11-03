#!/bin/sh
# Build the C++ research solver's tests and benchmark into the directory given, or ./build.
# Plain C++17 and the system clang; nothing from the engine.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/build"}
mkdir -p "$out"
flags="-std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter"
clang++ $flags -o "$out/tests" "$here/tests.cpp" "$here/wheel_solver.cpp"
clang++ $flags -o "$out/bench" "$here/bench.cpp" "$here/wheel_solver.cpp"
echo "built $out/tests and $out/bench"
