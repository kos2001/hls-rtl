// Gamma correction DUT.
//
//   1 pixel/cycle throughput, ready/valid handshake, per-channel LUT, 8b->8b.
//   The LUT is loaded through a simple write port (one channel/address per
//   cycle); swap it for an APB/AHB shim when integrating into a real SoC.
//
// Elastic datapath (FIFO_DEPTH-deep circular buffer):
//   * Post-LUT pixels are queued in a small FIFO; the head is presented on
//     out_* combinationally from registered state.
//   * in_ready = (count != FIFO_DEPTH) — registered occupancy only, so there
//     is NO combinational path from out_ready to in_ready (fully decoupled
//     handshake, no ready ripple).
//   * A 2-deep skid absorbed only single-cycle stalls; the test profiles stall
//     in bursts of 4-6 cycles, which overflowed it. FIFO_DEPTH (default 8)
//     absorbs those bursts and moves heavy-backpressure throughput toward the
//     elastic ideal (see TESTPLAN).
//   * Latency is still exactly 1 cycle from an accepted pixel to its output
//     when not stalled; the FIFO only fills during downstream stalls.
//   * Reset is asynchronous, active low; it clears the pointers/occupancy
//     (data storage needs no reset — out_valid gates garbage).
//
// Bit-exact contract (mirrored by golden + SystemC): output values are the
// per-channel LUT of each input pixel, in order. The FIFO changes
// timing/throughput only, never values or ordering.
//
// NOTE: pixels index the LUTs with their full PIXEL_W width, so the design
// assumes LUT_DEPTH == 2**PIXEL_W. The elaboration check below enforces it.

`default_nettype none

module gamma #(
    parameter integer PIXEL_W       = 8,
    parameter integer LUT_DEPTH     = 256,
    parameter integer FIFO_DEPTH    = 8,  // elastic depth, >= 2
    // 1 -> registered (synchronous) LUT read: BRAM-inferable on FPGA, shorter
    // LUT->register path, at the cost of one extra cycle of latency
    // (accept -> out_valid becomes 2 cycles). 0 -> combinational read, the
    // documented 1-cycle contract. Values/ordering identical either way.
    parameter integer LUT_SYNC_READ = 0
) (
    input  wire                          clk,
    input  wire                          rst_n,

    // pixel stream in
    input  wire                          in_valid,
    output wire                          in_ready,
    input  wire [PIXEL_W-1:0]            in_r,
    input  wire [PIXEL_W-1:0]            in_g,
    input  wire [PIXEL_W-1:0]            in_b,

    // pixel stream out
    output wire                          out_valid,
    input  wire                          out_ready,
    output wire [PIXEL_W-1:0]            out_r,
    output wire [PIXEL_W-1:0]            out_g,
    output wire [PIXEL_W-1:0]            out_b,

    // LUT write port (one channel/address per cycle)
    input  wire                          lut_we,
    input  wire [1:0]                    lut_ch,
    input  wire [$clog2(LUT_DEPTH)-1:0]  lut_addr,
    input  wire [PIXEL_W-1:0]            lut_wdata
);

    // Channel select encoding for lut_ch.
    localparam [1:0] CH_R = 2'b00,
                     CH_G = 2'b01,
                     CH_B = 2'b10;

    localparam integer PTR_W = $clog2(FIFO_DEPTH);
    localparam integer CNT_W = $clog2(FIFO_DEPTH + 1);

    // Elaboration-time guards.
    // synthesis translate_off
    initial begin
        if (LUT_DEPTH != (1 << PIXEL_W))
            $error("gamma: LUT_DEPTH (%0d) must equal 2**PIXEL_W (%0d)",
                   LUT_DEPTH, (1 << PIXEL_W));
        if (FIFO_DEPTH < 2)
            $error("gamma: FIFO_DEPTH (%0d) must be >= 2", FIFO_DEPTH);
    end
    // synthesis translate_on

    reg [PIXEL_W-1:0] lut_r_mem [0:LUT_DEPTH-1];
    reg [PIXEL_W-1:0] lut_g_mem [0:LUT_DEPTH-1];
    reg [PIXEL_W-1:0] lut_b_mem [0:LUT_DEPTH-1];

    // LUT write port: synchronous, one channel per cycle.
    always @(posedge clk) begin
        if (lut_we) begin
            case (lut_ch)
                CH_R:    lut_r_mem[lut_addr] <= lut_wdata;
                CH_G:    lut_g_mem[lut_addr] <= lut_wdata;
                CH_B:    lut_b_mem[lut_addr] <= lut_wdata;
                default: ; // reserved encoding -> no write
            endcase
        end
    end

    // Elastic FIFO of post-LUT pixels.
    reg [3*PIXEL_W-1:0] fifo_mem [0:FIFO_DEPTH-1];
    reg [PTR_W-1:0]     rd_ptr, wr_ptr;
    reg [CNT_W-1:0]     count;

    localparam integer     DEPTH_M1 = FIFO_DEPTH - 1;
    localparam [CNT_W-1:0] CNT_MAX  = FIFO_DEPTH[CNT_W-1:0];
    localparam [PTR_W-1:0] PTR_MAX  = DEPTH_M1[PTR_W-1:0];

    assign out_valid = (count != {CNT_W{1'b0}});

    wire push = in_valid & in_ready;
    wire pop  = out_valid & out_ready;

    wire                    fifo_push;
    wire [3*PIXEL_W-1:0]    fifo_wdata;

    generate
    if (LUT_SYNC_READ != 0) begin : g_lut_sync
        // Registered LUT read (BRAM pattern): the lookup is captured in a
        // register at the accept edge, then written into the FIFO one cycle
        // later. in_ready reserves the in-flight stage-1 entry so the FIFO
        // cannot overflow.
        reg                 s1_valid;
        reg [3*PIXEL_W-1:0] s1_data;
        always @(posedge clk or negedge rst_n)
            if (!rst_n) s1_valid <= 1'b0;
            else        s1_valid <= push;
        always @(posedge clk)
            if (push)
                s1_data <= {lut_r_mem[in_r], lut_g_mem[in_g], lut_b_mem[in_b]};
        assign fifo_push  = s1_valid;
        assign fifo_wdata = s1_data;
        assign in_ready   = ((count + {{(CNT_W-1){1'b0}}, s1_valid}) != CNT_MAX);
    end else begin : g_lut_async
        // Combinational read straight into the FIFO (1-cycle contract).
        wire [PIXEL_W-1:0] rd_r = lut_r_mem[in_r];
        wire [PIXEL_W-1:0] rd_g = lut_g_mem[in_g];
        wire [PIXEL_W-1:0] rd_b = lut_b_mem[in_b];
        assign fifo_push  = push;
        assign fifo_wdata = {rd_r, rd_g, rd_b};
        assign in_ready   = (count != CNT_MAX);
    end
    endgenerate

    // Head presented combinationally from registered state (1-cycle latency
    // from an accepted pixel: write at edge T, visible at T+1).
    assign {out_r, out_g, out_b} = fifo_mem[rd_ptr];

    // Data storage: plain synchronous write, no reset needed.
    always @(posedge clk) begin
        if (fifo_push)
            fifo_mem[wr_ptr] <= fifo_wdata;
    end

    // Pointers + occupancy.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_ptr <= {PTR_W{1'b0}};
            wr_ptr <= {PTR_W{1'b0}};
            count  <= {CNT_W{1'b0}};
        end else begin
            if (fifo_push)
                wr_ptr <= (wr_ptr == PTR_MAX) ? {PTR_W{1'b0}} : wr_ptr + {{(PTR_W-1){1'b0}}, 1'b1};
            if (pop)
                rd_ptr <= (rd_ptr == PTR_MAX) ? {PTR_W{1'b0}} : rd_ptr + {{(PTR_W-1){1'b0}}, 1'b1};
            count <= count + {{(CNT_W-1){1'b0}}, fifo_push} - {{(CNT_W-1){1'b0}}, pop};
        end
    end

endmodule

`default_nettype wire
