// SystemC cycle-accurate model of gamma correction.
// Mirrors rtl/gamma.v: 1 cycle latency, ready/valid handshake, per-channel LUT.

#ifndef GAMMA_SC_H
#define GAMMA_SC_H

#include <systemc.h>

template <int PIXEL_W = 8, int LUT_DEPTH = 256>
SC_MODULE(gamma_sc) {
    sc_in<bool>  clk;
    sc_in<bool>  rst_n;

    sc_in<bool>            in_valid;
    sc_out<bool>           in_ready;
    sc_in<sc_uint<PIXEL_W>> in_r, in_g, in_b;

    sc_out<bool>            out_valid;
    sc_in<bool>             out_ready;
    sc_out<sc_uint<PIXEL_W>> out_r, out_g, out_b;

    sc_in<bool>            lut_we;
    sc_in<sc_uint<2>>      lut_ch;
    sc_in<sc_uint<32>>     lut_addr;
    sc_in<sc_uint<PIXEL_W>> lut_wdata;

    sc_uint<PIXEL_W> lut_r_mem[LUT_DEPTH];
    sc_uint<PIXEL_W> lut_g_mem[LUT_DEPTH];
    sc_uint<PIXEL_W> lut_b_mem[LUT_DEPTH];

    // Elastic FIFO of post-LUT pixels — mirrors rtl/gamma.v (FIFO_DEPTH deep,
    // in_ready = count != FIFO_DEPTH, head presented from registered state).
    // NOTE: mirrors the default LUT_SYNC_READ=0 configuration; the RTL's
    // opt-in registered-LUT-read mode differs in latency only (values/order
    // identical, verified against the golden scoreboard).
    static const int FIFO_DEPTH = 8;
    sc_uint<PIXEL_W> fifo_r[FIFO_DEPTH], fifo_g[FIFO_DEPTH], fifo_b[FIFO_DEPTH];
    int rd_ptr = 0, wr_ptr = 0, count = 0;

    void seq();

    SC_CTOR(gamma_sc) {
        SC_METHOD(seq);
        sensitive << clk.pos();
        async_reset_signal_is(rst_n, false);
    }
};

#endif
