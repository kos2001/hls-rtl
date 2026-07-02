// Standalone SystemC simulator: reads stim.txt, writes sc_out.txt.
// Format (stim): one pixel per line "R G B" in decimal. LUT loaded from lut.txt:
// "ch addr value" lines, sentinel "GO" starts streaming.
//
// Output (sc_out.txt): "R G B" per produced pixel in order.

#include <fstream>
#include <iostream>
#include <sstream>
#include "gamma_sc.h"

int sc_main(int argc, char** argv) {
    sc_clock clk("clk", 10, SC_NS);
    sc_signal<bool> rst_n;
    sc_signal<bool> in_valid, in_ready;
    sc_signal<sc_uint<8>> in_r, in_g, in_b;
    sc_signal<bool> out_valid, out_ready;
    sc_signal<sc_uint<8>> out_r, out_g, out_b;
    sc_signal<bool> lut_we;
    sc_signal<sc_uint<2>> lut_ch;
    sc_signal<sc_uint<32>> lut_addr;
    sc_signal<sc_uint<8>> lut_wdata;

    gamma_sc<8, 256> dut("dut");
    dut.clk(clk); dut.rst_n(rst_n);
    dut.in_valid(in_valid); dut.in_ready(in_ready);
    dut.in_r(in_r); dut.in_g(in_g); dut.in_b(in_b);
    dut.out_valid(out_valid); dut.out_ready(out_ready);
    dut.out_r(out_r); dut.out_g(out_g); dut.out_b(out_b);
    dut.lut_we(lut_we); dut.lut_ch(lut_ch);
    dut.lut_addr(lut_addr); dut.lut_wdata(lut_wdata);

    std::ofstream fout("sc_out.txt");
    out_ready.write(true);
    rst_n.write(false);
    sc_start(20, SC_NS);
    rst_n.write(true);

    std::ifstream flut("lut.txt");
    std::string line;
    while (std::getline(flut, line)) {
        if (line == "GO") break;
        std::istringstream iss(line);
        unsigned ch, addr, val;
        iss >> ch >> addr >> val;
        lut_we.write(true);
        lut_ch.write(ch); lut_addr.write(addr); lut_wdata.write(val);
        sc_start(10, SC_NS);
    }
    lut_we.write(false);

    std::ifstream fin("stim.txt");
    while (std::getline(fin, line)) {
        std::istringstream iss(line);
        unsigned r, g, b;
        iss >> r >> g >> b;
        in_valid.write(true);
        in_r.write(r); in_g.write(g); in_b.write(b);
        sc_start(10, SC_NS);
        if (out_valid.read()) {
            fout << out_r.read() << " " << out_g.read() << " " << out_b.read() << "\n";
        }
    }
    in_valid.write(false);
    for (int i = 0; i < 4; ++i) {
        sc_start(10, SC_NS);
        if (out_valid.read()) {
            fout << out_r.read() << " " << out_g.read() << " " << out_b.read() << "\n";
        }
    }
    return 0;
}
