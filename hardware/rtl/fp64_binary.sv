// Combinational FP64 operation with one rounding after each add/subtract/multiply.
// Finite inputs and gradual underflow are supported; there is no FMA.
`include "HardFloat_consts.vi"
`include "HardFloat_specialize.vi"
module fp64_binary (
    input  logic        multiply,
    input  logic        subtract,
    input  logic [63:0] a,
    input  logic [63:0] b,
    output logic [63:0] result,
    output logic [4:0]  exception_flags
);
    wire [64:0] rec_a, rec_b, add_result, mul_result;
    wire [63:0] add_ieee, mul_ieee;
    wire [4:0] add_flags, mul_flags;
    fNToRecFN #(.expWidth(11), .sigWidth(53)) decode_a (.in(a), .out(rec_a));
    fNToRecFN #(.expWidth(11), .sigWidth(53)) decode_b (.in(b), .out(rec_b));
    addRecFN #(.expWidth(11), .sigWidth(53)) add_sub (
        .control(`flControl_tininessAfterRounding), .subOp(subtract),
        .a(rec_a), .b(rec_b), .roundingMode(`round_near_even),
        .out(add_result), .exceptionFlags(add_flags)
    );
    mulRecFN #(.expWidth(11), .sigWidth(53)) mul (
        .control(`flControl_tininessAfterRounding), .a(rec_a), .b(rec_b),
        .roundingMode(`round_near_even), .out(mul_result), .exceptionFlags(mul_flags)
    );
    recFNToFN #(.expWidth(11), .sigWidth(53)) encode_add (.in(add_result), .out(add_ieee));
    recFNToFN #(.expWidth(11), .sigWidth(53)) encode_mul (.in(mul_result), .out(mul_ieee));
    assign result = multiply ? mul_ieee : add_ieee;
    assign exception_flags = multiply ? mul_flags : add_flags;
endmodule
