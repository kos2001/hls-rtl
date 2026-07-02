# cocotb + Verilator
#
# Performance knobs:
#   make                -> fast "split" run (data + protocol phases)
#   make WAVES=1        -> add VCD waveform dump (~30% slower)
#   BP_PROFILE=full make -> exhaustive pattern x profile cross-product (nightly)
#   BP_PROFILE=single make -> one env-defined profile across all patterns (debug)
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

ROOT := $(shell cd .. && pwd)
VERILOG_SOURCES := $(ROOT)/rtl/gamma.v
TOPLEVEL := gamma
MODULE := test_gamma

# Waveform tracing is opt-in: `make WAVES=1` (VCD dump costs ~30% sim time).
ifeq ($(WAVES),1)
EXTRA_ARGS += --trace --trace-structs
endif
# Verilator C++ optimization; compile-time cost is negligible for this design.
EXTRA_ARGS += -O3

include $(shell cocotb-config --makefiles)/Makefile.sim
