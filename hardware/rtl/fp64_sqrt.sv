// Iterative, correctly rounded FP64 square root; out_valid is a one-cycle pulse.
`include "HardFloat_consts.vi"
`include "HardFloat_specialize.vi"
module fp64_sqrt (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        in_valid,
    output logic        in_ready,
    input  logic [63:0] operand,
    output logic        out_valid,
    output logic [63:0] result,
    output logic [4:0]  exception_flags
);
    wire [64:0] rec_operand, rec_result;
    wire sqrt_op_unused;
    fNToRecFN #(.expWidth(11), .sigWidth(53)) decode (.in(operand), .out(rec_operand));
    divSqrtRecFN_small #(.expWidth(11), .sigWidth(53), .options(0)) sqrt_unit (
        .nReset(rst_n), .clock(clk), .control(`flControl_tininessAfterRounding),
        .inReady(in_ready), .inValid(in_valid), .sqrtOp(1'b1),
        .a(rec_operand), .b(65'b0), .roundingMode(`round_near_even),
        .outValid(out_valid), .sqrtOpOut(sqrt_op_unused),
        .out(rec_result), .exceptionFlags(exception_flags)
    );
    recFNToFN #(.expWidth(11), .sigWidth(53)) encode (.in(rec_result), .out(result));
endmodule
