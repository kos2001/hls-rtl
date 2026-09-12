// Formal properties for rtl/gamma.v — black box, ports only.
//
// WHY THESE EXIST
// ---------------
// The scoreboard has a MEASURED blind spot. Changing `in_ready` to
// `count != CNT_MAX-1` (an effective depth of 7) passes 13/13 patterns with
// 0.0% throughput change on every backpressure profile: the scoreboard proves
// values and ordering, and buffer depth moves neither. Simulation cannot see
// that bug. An invariant can.
//
// WHY NOTHING REACHES INTO THE DUT
// --------------------------------
// The first version asserted on `dut.count`. Yosys does not support
// hierarchical references: it implicitly declares `\dut.count` as a wire with
// no driver, which in formal is a FREE VARIABLE. The tool says so only as a
// warning —
//     Warning: Identifier `\dut.count' is implicitly declared.
//     Warning: Wire m.\dut.count is used but has no driver.
// — and the suite still "runs", reporting spurious counterexamples while the
// property that was supposed to catch the depth-7 mutant quietly proved nothing.
//
// So occupancy is reconstructed here from the handshakes alone. That is better
// formal engineering regardless: the properties then constrain the DUT's
// observable contract instead of assuming its internal representation, and they
// keep holding if the implementation is rewritten.
//
// Parameters are shrunk for tractability. These are control-path invariants
// (occupancy, handshake, stability) — parameter-shaped, not parameter-valued.
// The datapath is what the golden-model scoreboard covers.

`default_nettype none

module gamma_props #(
    parameter integer PIXEL_W       = 2,
    parameter integer LUT_DEPTH     = 4,
    parameter integer FIFO_DEPTH    = 4,
    // The DUT supports a registered-LUT-read mode whose `generate` branch the
    // default elaboration never builds. Mutation testing found an occupancy
    // off-by-one surviving in there: the `configs` simulation stage compares
    // values, and depth is timing-only, so only an invariant can see it — and
    // the invariants were not running in that configuration either.
    parameter integer LUT_SYNC_READ = 0
) (
    input wire clk,
    input wire rst_n,

    input wire                          in_valid,
    input wire [PIXEL_W-1:0]            in_r, in_g, in_b,
    input wire                          out_ready,
    input wire                          lut_we,
    input wire [1:0]                    lut_ch,
    input wire [$clog2(LUT_DEPTH)-1:0]  lut_addr,
    input wire [PIXEL_W-1:0]            lut_wdata
);

    wire                in_ready, out_valid;
    wire [PIXEL_W-1:0]  out_r, out_g, out_b;

    gamma #(
        .PIXEL_W(PIXEL_W), .LUT_DEPTH(LUT_DEPTH), .FIFO_DEPTH(FIFO_DEPTH),
        .LUT_SYNC_READ(LUT_SYNC_READ)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .in_valid(in_valid), .in_ready(in_ready),
        .in_r(in_r), .in_g(in_g), .in_b(in_b),
        .out_valid(out_valid), .out_ready(out_ready),
        .out_r(out_r), .out_g(out_g), .out_b(out_b),
        .lut_we(lut_we), .lut_ch(lut_ch),
        .lut_addr(lut_addr), .lut_wdata(lut_wdata)
    );

    localparam integer CNT_W = $clog2(FIFO_DEPTH + 1);
    localparam integer PTR_W = $clog2(FIFO_DEPTH);

    wire push = in_valid  && in_ready;
    wire pop  = out_valid && out_ready;

    // The DUT's own occupancy counter, bound by a yosys `connect` in gamma.sby
    // AFTER `flatten` — see the note there. It is used for exactly one thing:
    // the induction-strengthening invariant A9. Every behavioural property
    // below still speaks only about the ports.
    //
    // If the internal name ever changes, `connect -set` fails with a hard error
    // ("Failed to parse set rhs expression"), not a warning. That matters: the
    // Verilog frontend's response to the same mistake is to invent an undriven
    // wire — a free variable that makes properties pass while proving nothing.
    wire [CNT_W-1:0] dut_count;
    wire [PTR_W-1:0] dut_rd_ptr, dut_wr_ptr;
    // Accepted but not yet written into the FIFO. Zero in the default mode;
    // in registered-read mode it is the in-flight stage-1 entry. Bound by
    // `connect` per task, to a constant or to the real signal.
    wire             dut_pending;

    // Reference occupancy: how many pixels the DUT has accepted but not yet
    // handed over. Driven purely by the handshakes, with the DUT's own reset
    // semantics (asynchronous, active low).
    reg [CNT_W-1:0] outstanding;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) outstanding <= {CNT_W{1'b0}};
        else        outstanding <= outstanding
                                 + {{(CNT_W-1){1'b0}}, push}
                                 - {{(CNT_W-1){1'b0}}, pop};

    // ---- history ----
    reg seen = 1'b0;
    reg p_rst_n, p_in_valid, p_in_ready, p_out_valid, p_out_ready;
    reg [PIXEL_W-1:0] p_in_r, p_in_g, p_in_b, p_out_r, p_out_g, p_out_b;

    always @(posedge clk) begin
        seen        <= 1'b1;
        p_rst_n     <= rst_n;
        p_in_valid  <= in_valid;
        p_in_ready  <= in_ready;
        p_out_valid <= out_valid;
        p_out_ready <= out_ready;
        p_in_r <= in_r;   p_in_g <= in_g;   p_in_b <= in_b;
        p_out_r <= out_r; p_out_g <= out_g; p_out_b <= out_b;
    end

    // ---- environment ----
    //
    // Boot: hold reset across two clock edges, then let rst_n go free.
    //
    // Two edges because the DUT's registers have no initial value — at step 0
    // they are free, and an asynchronous reset is part of the next-state
    // function, so it has not been applied yet. Free AFTERWARDS rather than
    // pinned high, because pinning it would make the reset property vacuous, and
    // a vacuously passing reset property is worse than none.
    reg [1:0] boot = 2'd0;
    always @(posedge clk) if (boot != 2'd2) boot <= boot + 2'd1;
    wire booted = (boot == 2'd2);

    initial assume (!rst_n);

    always @(posedge clk) begin
        if (!booted) assume (!rst_n);

        // A legal ready/valid source: valid, once raised, holds with stable data
        // until it is accepted. Without this the solver invents a stream no
        // interconnect would produce and the counterexamples describe the
        // testbench rather than the DUT.
        if (seen && p_rst_n && rst_n && p_in_valid && !p_in_ready) begin
            assume (in_valid);
            assume (in_r == p_in_r);
            assume (in_g == p_in_g);
            assume (in_b == p_in_b);
        end
    end

    // ---- safety ----
    always @(posedge clk) if (booted) begin

        // A1. The DUT never accepts more than it can hold. With A3 this is what
        //     makes overflow impossible rather than merely unobserved.
        a_no_overflow: assert (outstanding <= FIFO_DEPTH[CNT_W-1:0]);

        if (rst_n) begin
            // A2. No false backpressure: while it has room, the core must
            //     accept. THIS is the property the depth-7 mutant violates, and
            //     the reason this file exists.
            a_no_false_stall: assert (!(outstanding < FIFO_DEPTH[CNT_W-1:0]) || in_ready);

            // A3. A full buffer must refuse.
            a_full_refuses: assert (!(outstanding == FIFO_DEPTH[CNT_W-1:0]) || !in_ready);

            // A4. Output validity is exactly "something is ready to hand over".
            //     Outstanding minus whatever is still in flight: in the default
            //     mode nothing is, and the two agree; in registered-read mode a
            //     pixel spends one cycle in stage 1 before it is presentable,
            //     and counting it would make this assert a latency claim rather
            //     than a validity one.
            a_valid_iff_outstanding: assert (
                out_valid == ((outstanding - {{(CNT_W-1){1'b0}}, dut_pending})
                              != {CNT_W{1'b0}}));

            // A6. No retraction: a presented pixel stays presented, unchanged,
            //     until the sink takes it. A stalling sink must not lose data.
            //     Guarded on p_rst_n: a reset legitimately drops the output.
            if (seen && p_rst_n && p_out_valid && !p_out_ready) begin
                a_no_retraction: assert (out_valid);
                a_data_stable_r: assert (out_r == p_out_r);
                a_data_stable_g: assert (out_g == p_out_g);
                a_data_stable_b: assert (out_b == p_out_b);
            end
        end

        // A9. The reference model tracks the DUT's own counter.
        //
        //     This is the ONE property that names an internal signal, and it
        //     exists to make k-induction close. Induction starts from an
        //     arbitrary state satisfying the assertions; without this, it may
        //     start with `outstanding` and the DUT's counter disagreeing in a
        //     way no reachable execution allows, and A2/A4 then fail in the
        //     inductive step for a reason that cannot happen. Both counters
        //     move by the same push/pop under the same reset, so the equality
        //     is itself inductive.
        //
        //     It is not a restatement of the behavioural properties: those say
        //     what the ports must do, this says the model is watching the right
        //     register.
        a_model_tracks_dut: assert (
            outstanding == dut_count + {{(CNT_W-1){1'b0}}, dut_pending});

        // A11. The DUT's own counter is bounded.
        //
        //      Not implied by A1 + A9, which is the trap: A9 is modular
        //      arithmetic in CNT_W bits, so a garbage state with dut_count = 7
        //      and dut_pending = 1 satisfies it by wrapping to 0 and matching an
        //      `outstanding` of 0. Induction started exactly there and then
        //      violated A1 one step later. Bounding the counter itself is what
        //      rules the state out.
        a_dut_count_bounded: assert (dut_count <= FIFO_DEPTH[CNT_W-1:0]);

        // A10. The pointers agree with the occupancy.
        //
        //      The second induction strengthener, and the one the data-stability
        //      properties need. Without it, induction may begin in a state where
        //      the FIFO is not full yet `wr_ptr == rd_ptr`; a push then
        //      overwrites the entry currently being presented, and A6 fails for
        //      a reason no reachable execution can produce.
        //
        //      FIFO_DEPTH is a power of two here, so truncating the count to
        //      PTR_W bits is the modulo: at count == FIFO_DEPTH it gives 0,
        //      which is exactly the full case where the pointers coincide.
        a_ptrs_match_count: assert (dut_wr_ptr == (dut_rd_ptr + dut_count[PTR_W-1:0]));

        // A8. Reset empties the core. Stated on the current cycle because the
        //     reset is asynchronous: it holds while rst_n is low, not one cycle
        //     after release. (Stating it the other way is a real trap — an early
        //     version failed on a reset released by the same edge that accepted
        //     a pixel, which made a non-zero occupancy correct.)
        if (!rst_n)
            a_reset_empties: assert (!out_valid);
    end

    // ---- cover: these states must be reachable, or a passing proof is vacuous ----
    always @(posedge clk) if (booted) begin
        c_fills:     cover (rst_n && outstanding == FIFO_DEPTH[CNT_W-1:0]);
        c_drains:    cover (rst_n && seen && p_out_valid && outstanding == {CNT_W{1'b0}});
        c_stall:     cover (rst_n && out_valid && !out_ready);
        c_full_rate: cover (rst_n && push && pop);
    end

endmodule

`default_nettype wire
