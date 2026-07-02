#include "gamma_sc.h"

template <int PIXEL_W, int LUT_DEPTH>
void gamma_sc<PIXEL_W, LUT_DEPTH>::seq() {
    if (!rst_n.read()) {
        out_valid.write(false);
        out_r.write(0); out_g.write(0); out_b.write(0);
        rd_ptr = wr_ptr = count = 0;
        in_ready.write(true);   // empty -> ready
        return;
    }

    if (lut_we.read()) {
        unsigned a = lut_addr.read().to_uint();
        switch (lut_ch.read().to_uint()) {
            case 0: lut_r_mem[a] = lut_wdata.read(); break;
            case 1: lut_g_mem[a] = lut_wdata.read(); break;
            case 2: lut_b_mem[a] = lut_wdata.read(); break;
        }
    }

    // Elastic FIFO, mirroring rtl/gamma.v. Decisions use the pre-edge
    // (registered) occupancy; outputs reflect post-edge state.
    bool ready = (count != FIFO_DEPTH);
    bool push  = in_valid.read() && ready;
    bool pop   = (count != 0) && out_ready.read();

    if (push) {
        fifo_r[wr_ptr] = lut_r_mem[in_r.read().to_uint()];
        fifo_g[wr_ptr] = lut_g_mem[in_g.read().to_uint()];
        fifo_b[wr_ptr] = lut_b_mem[in_b.read().to_uint()];
        wr_ptr = (wr_ptr + 1) % FIFO_DEPTH;
    }
    if (pop)
        rd_ptr = (rd_ptr + 1) % FIFO_DEPTH;
    count += (push ? 1 : 0) - (pop ? 1 : 0);

    in_ready.write(count != FIFO_DEPTH);
    out_valid.write(count != 0);
    if (count != 0) {
        out_r.write(fifo_r[rd_ptr]);
        out_g.write(fifo_g[rd_ptr]);
        out_b.write(fifo_b[rd_ptr]);
    }
}

template struct gamma_sc<8, 256>;
