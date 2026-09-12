#!/usr/bin/env bash
# Build the standalone SystemC simulator.
#
# The SystemC rung is the third model in a scoreboard that calls itself 3-way,
# and it is the one that silently disappears: when build/sc_out.txt is absent the
# comparison is SKIPPED, not failed, so the suite stays green while proving one
# third less. This script exists so building it is one command rather than a
# long g++ line that lives only in a README.
#
# SYSTEMC_HOME is honoured if set; otherwise the usual install locations are
# searched, so `brew install systemc` is enough on a fresh machine.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/build"

find_systemc() {
    if [[ -n "${SYSTEMC_HOME:-}" && -f "$SYSTEMC_HOME/include/systemc.h" ]]; then
        echo "$SYSTEMC_HOME"; return
    fi
    local candidates=()
    if command -v brew >/dev/null 2>&1; then
        candidates+=("$(brew --prefix systemc 2>/dev/null || true)")
    fi
    candidates+=(/opt/homebrew/opt/systemc /usr/local/systemc /opt/systemc
                 /usr/local /usr "$HOME/systemc")
    for c in "${candidates[@]}"; do
        [[ -n "$c" && -f "$c/include/systemc.h" ]] && { echo "$c"; return; }
    done
}

SC="$(find_systemc || true)"
if [[ -z "$SC" ]]; then
    cat >&2 <<'MSG'
SystemC not found. Install it, or set SYSTEMC_HOME:

    brew install systemc                 # macOS
    sudo apt install libsystemc-dev      # Debian/Ubuntu
    SYSTEMC_HOME=/path/to/systemc scripts/build_systemc.sh

Without it the SystemC comparison is skipped — which is missing evidence, not a
pass. The RTL-vs-golden comparison still gates.
MSG
    exit 2
fi

# SystemC 3.x needs C++17 or later; the models are written to that standard.
mkdir -p "$BUILD"
echo "SystemC: $SC"
g++ -std=c++17 \
    -I"$SC/include" -L"$SC/lib" \
    "$ROOT/systemc/sim_main.cpp" "$ROOT/systemc/gamma_sc.cpp" \
    -lsystemc -Wl,-rpath,"$SC/lib" \
    -o "$BUILD/gamma_sc_sim"
echo "built: build/gamma_sc_sim"
