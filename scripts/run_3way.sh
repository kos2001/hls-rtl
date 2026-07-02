#!/usr/bin/env bash
# 3-way regression: golden (in-process) + SystemC (separate sim) + RTL (cocotb).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
mkdir -p "$BUILD"

echo "[0/3] Running Python unit tests (golden model + stimulus + test set)"
python3 -m pytest "$ROOT/tests" -q

echo "[1/3] Generating SystemC inputs"
python3 "$ROOT/scripts/gen_sc_inputs.py"

echo "[2/3] Running SystemC simulator"
if [[ -x "$BUILD/gamma_sc_sim" ]]; then
  ( cd "$BUILD" && ./gamma_sc_sim )
else
  echo "  (skip) build SystemC sim first:"
  echo "    g++ -std=c++17 -I\$SYSTEMC_HOME/include -L\$SYSTEMC_HOME/lib \\"
  echo "        $ROOT/systemc/sim_main.cpp $ROOT/systemc/gamma_sc.cpp \\"
  echo "        -lsystemc -o $BUILD/gamma_sc_sim"
fi

echo "[3/3] Running cocotb (RTL) + Python golden scoreboard"
cd "$ROOT/tb"
make
