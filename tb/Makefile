# cocotb testbench driver.
#
#   make                    -> fast "split" run under Verilator (data + protocol)
#   make SIM=icarus         -> 4-state cross-check (X/Z, reset initialization)
#   make WAVES=1            -> VCD waveform dump (~30% slower)
#   BP_PROFILE=full make    -> exhaustive pattern x profile cross-product (nightly)
#   BP_PROFILE=single make  -> one env-defined profile across all patterns (debug)
#
# Two simulators on purpose. Verilator is fast but 2-state: it cannot represent
# X, so it cannot find an uninitialized read or a reset that fails to clear.
# Icarus is slower and 4-state, and is the only thing here that can. Neither
# replaces the other.
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

ROOT := $(shell cd .. && pwd)
VERILOG_SOURCES := $(ROOT)/rtl/gamma.v
TOPLEVEL := gamma
MODULE := test_gamma

# Simulator flags must be guarded by simulator. `-O3` and `--trace` are
# Verilator's; passing them to Icarus fails at compile with
# `illegal option -- O`, which is what `make SIM=icarus` used to do.
ifeq ($(SIM),verilator)
  # Verilator C++ optimisation; compile cost is negligible for this design.
  EXTRA_ARGS += -O3
  ifeq ($(WAVES),1)
    EXTRA_ARGS += --trace --trace-structs
  endif
endif

# Icarus handles WAVES itself (cocotb's Makefile.icarus injects the dump
# module), so nothing is added here for it.

include $(shell cocotb-config --makefiles)/Makefile.sim
