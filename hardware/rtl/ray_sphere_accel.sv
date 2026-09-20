// Sequential implementation of upstream Sphere.intersectionTime's FP64 formula.
// Ports use IEEE binary64 bits, not SystemVerilog real values.
// Request words [64*i +: 64]: origin xyz, direction xyz, center xyz, radius.
// Direction must already be normalized by the caller, as in upstream Ray.
module ray_sphere_accel (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         in_valid,
    output logic         in_ready,
    input  logic [639:0] in_data,
    input  logic [31:0]  in_tag,
    output logic         out_valid,
    input  logic         out_ready,
    output logic [63:0]  out_t,
    output logic [31:0]  out_tag,
    output logic         out_has_root,
    output logic         out_error,
    output logic [4:0]   out_exception_flags
);
    typedef enum logic [2:0] {IDLE, CALCULATE, CHECK_DISC, SQRT_ISSUE,
                             SQRT_WAIT, FINAL_SUBTRACT, RESPONSE} state_t;
    state_t state;
    logic [4:0] step;
    logic [63:0] origin [0:2], direction [0:2], center [0:2];
    logic [63:0] radius, cp [0:2];
    logic [63:0] product0, product1, partial_sum, v, radius_squared;
    logic [63:0] cp_squared, v_squared, difference, discriminant, square_root;
    logic input_invalid;
    logic [63:0] alu_a, alu_b;
    logic alu_multiply, alu_subtract;
    wire [63:0] alu_result, sqrt_result;
    wire [4:0] alu_flags, sqrt_flags;
    wire sqrt_ready, sqrt_valid;
    wire sqrt_request = (state == SQRT_ISSUE) && rst_n;

    function automatic logic nonfinite(input logic [63:0] value);
        nonfinite = (value[62:52] == 11'h7ff);
    endfunction

    always_comb begin
        input_invalid = 1'b0;
        for (int i = 0; i < 10; i++)
            input_invalid = input_invalid | nonfinite(in_data[64*i +: 64]);
        // Negative zero is permitted; negative nonzero radii are rejected.
        input_invalid = input_invalid | (in_data[639] && (|in_data[638:576]));
    end

    assign in_ready = rst_n && (state == IDLE);
    assign out_valid = rst_n && (state == RESPONSE);

    fp64_binary alu (
        .multiply(alu_multiply), .subtract(alu_subtract), .a(alu_a), .b(alu_b),
        .result(alu_result), .exception_flags(alu_flags)
    );
    fp64_sqrt sqrt_datapath (
        .clk(clk), .rst_n(rst_n), .in_valid(sqrt_request), .in_ready(sqrt_ready),
        .operand(discriminant), .out_valid(sqrt_valid), .result(sqrt_result),
        .exception_flags(sqrt_flags)
    );

    // Each step uses a rounded FP64 result, preserving Python's expression tree.
    always_comb begin
        alu_a = 64'b0;
        alu_b = 64'b0;
        alu_multiply = 1'b0;
        alu_subtract = 1'b0;
        if (state == CALCULATE) begin
            case (step)
                 0: begin alu_a=center[0]; alu_b=origin[0]; alu_subtract=1'b1; end
                 1: begin alu_a=center[1]; alu_b=origin[1]; alu_subtract=1'b1; end
                 2: begin alu_a=center[2]; alu_b=origin[2]; alu_subtract=1'b1; end
                 3: begin alu_a=cp[0]; alu_b=direction[0]; alu_multiply=1'b1; end
                 4: begin alu_a=cp[1]; alu_b=direction[1]; alu_multiply=1'b1; end
                 5: begin alu_a=product0; alu_b=product1; end
                 6: begin alu_a=cp[2]; alu_b=direction[2]; alu_multiply=1'b1; end
                 7: begin alu_a=partial_sum; alu_b=product0; end
                 8: begin alu_a=radius; alu_b=radius; alu_multiply=1'b1; end
                 9: begin alu_a=cp[0]; alu_b=cp[0]; alu_multiply=1'b1; end
                10: begin alu_a=cp[1]; alu_b=cp[1]; alu_multiply=1'b1; end
                11: begin alu_a=product0; alu_b=product1; end
                12: begin alu_a=cp[2]; alu_b=cp[2]; alu_multiply=1'b1; end
                13: begin alu_a=partial_sum; alu_b=product0; end
                14: begin alu_a=v; alu_b=v; alu_multiply=1'b1; end
                15: begin alu_a=cp_squared; alu_b=v_squared; alu_subtract=1'b1; end
                16: begin alu_a=radius_squared; alu_b=difference; alu_subtract=1'b1; end
                default: begin end
            endcase
        end else if (state == FINAL_SUBTRACT) begin
            alu_a = v;
            alu_b = square_root;
            alu_subtract = 1'b1;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            step <= 5'b0;
            out_t <= 64'b0;
            out_tag <= 32'b0;
            out_has_root <= 1'b0;
            out_error <= 1'b0;
            out_exception_flags <= 5'b0;
            // Datapath registers need no reset: every consumed value is written
            // after request acceptance before its first use. Outputs ARE reset.
        end else begin
            case (state)
                IDLE: begin
                    if (in_valid) begin
                        out_tag <= in_tag;
                        out_t <= 64'b0;
                        out_has_root <= 1'b0;
                        out_error <= input_invalid;
                        out_exception_flags <= 5'b0;
                        if (input_invalid) begin
                            state <= RESPONSE;
                        end else begin
                            for (int i = 0; i < 3; i++) begin
                                origin[i] <= in_data[64*i +: 64];
                                direction[i] <= in_data[64*(i+3) +: 64];
                                center[i] <= in_data[64*(i+6) +: 64];
                            end
                            radius <= in_data[576 +: 64];
                            step <= 5'b0;
                            state <= CALCULATE;
                        end
                    end
                end
                CALCULATE: begin
                    out_exception_flags <= out_exception_flags | alu_flags;
                    if (nonfinite(alu_result) || (|alu_flags[4:2])) begin
                        out_error <= 1'b1;
                        state <= RESPONSE;
                    end else begin
                        case (step)
                             0: cp[0] <= alu_result;
                             1: cp[1] <= alu_result;
                             2: cp[2] <= alu_result;
                             3: product0 <= alu_result;
                             4: product1 <= alu_result;
                             5: partial_sum <= alu_result;
                             6: product0 <= alu_result;
                             7: v <= alu_result;
                             8: radius_squared <= alu_result;
                             9: product0 <= alu_result;
                            10: product1 <= alu_result;
                            11: partial_sum <= alu_result;
                            12: product0 <= alu_result;
                            13: cp_squared <= alu_result;
                            14: v_squared <= alu_result;
                            15: difference <= alu_result;
                            16: discriminant <= alu_result;
                            default: begin out_error <= 1'b1; state <= RESPONSE; end
                        endcase
                        if (step == 16) state <= CHECK_DISC;
                        else step <= step + 1'b1;
                    end
                end
                CHECK_DISC: begin
                    if (discriminant[63] && (|discriminant[62:0])) begin
                        // Negative t is not a miss; only a negative discriminant
                        // yields upstream None. Caller applies its own epsilon.
                        state <= RESPONSE;
                    end else begin
                        state <= SQRT_ISSUE;
                    end
                end
                SQRT_ISSUE: begin
                    if (sqrt_ready) state <= SQRT_WAIT;
                end
                SQRT_WAIT: begin
                    if (sqrt_valid) begin
                        out_exception_flags <= out_exception_flags | sqrt_flags;
                        if (nonfinite(sqrt_result) || (|sqrt_flags[4:2])) begin
                            out_error <= 1'b1;
                            state <= RESPONSE;
                        end else begin
                            square_root <= sqrt_result;
                            state <= FINAL_SUBTRACT;
                        end
                    end
                end
                FINAL_SUBTRACT: begin
                    out_exception_flags <= out_exception_flags | alu_flags;
                    if (nonfinite(alu_result) || (|alu_flags[4:2])) begin
                        out_error <= 1'b1;
                    end else begin
                        out_t <= alu_result;
                        out_has_root <= 1'b1;
                    end
                    state <= RESPONSE;
                end
                RESPONSE: begin
                    // Results, tag and flags remain stable through backpressure.
                    if (out_ready) state <= IDLE;
                end
                default: begin
                    out_error <= 1'b1;
                    out_has_root <= 1'b0;
                    out_t <= 64'b0;
                    state <= RESPONSE;
                end
            endcase
        end
    end
endmodule
