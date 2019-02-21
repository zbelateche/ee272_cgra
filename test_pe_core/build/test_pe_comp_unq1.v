//
//--------------------------------------------------------------------------------
//          THIS FILE WAS AUTOMATICALLY GENERATED BY THE GENESIS2 ENGINE        
//  FOR MORE INFORMATION: OFER SHACHAM (CHIP GENESIS INC / STANFORD VLSI GROUP)
//    !! THIS VERSION OF GENESIS2 IS NOT FOR ANY COMMERCIAL USE !!
//     FOR COMMERCIAL LICENSE CONTACT SHACHAM@ALUMNI.STANFORD.EDU
//--------------------------------------------------------------------------------
//
//  
//	-----------------------------------------------
//	|            Genesis Release Info             |
//	|  $Change: 11904 $ --- $Date: 2013/08/03 $   |
//	-----------------------------------------------
//	
//
//  Source file: /home/zach/Documents/Stanford/classes/ee272/garnet/pe_core/genesis/test_pe_comp.svp
//  Source template: test_pe_comp
//
// --------------- Begin Pre-Generation Parameters Status Report ---------------
//
//	From 'generate' statement (priority=5):
// Parameter use_cntr 	= 0
// Parameter use_div 	= 0
// Parameter use_add 	= 1
// Parameter use_shift 	= 1
// Parameter en_ovfl 	= 1
// Parameter use_max_min 	= 1
// Parameter debug 	= 0
// Parameter is_msb 	= 0
// Parameter use_relu 	= 0
// Parameter use_bool 	= 1
// Parameter en_double 	= 0
// Parameter en_opt 	= 1
// Parameter get_carry 	= 1
// Parameter use_abs 	= 1
// Parameter en_trick 	= 0
// Parameter mult_mode 	= 1
//
//		---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ----
//
//	From Command Line input (priority=4):
//
//		---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ----
//
//	From XML input (priority=3):
//
//		---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ----
//
//	From Config File input (priority=2):
//
// ---------------- End Pre-Generation Pramameters Status Report ----------------

// data_width (_GENESIS2_DECLARATION_PRIORITY_) = 16
//
// use_add (_GENESIS2_INHERITANCE_PRIORITY_) = 1
//
// use_cntr (_GENESIS2_INHERITANCE_PRIORITY_) = 0
//
// use_bool (_GENESIS2_INHERITANCE_PRIORITY_) = 1
//
// use_shift (_GENESIS2_INHERITANCE_PRIORITY_) = 1
//
// mult_mode (_GENESIS2_INHERITANCE_PRIORITY_) = 1
//
// use_div (_GENESIS2_INHERITANCE_PRIORITY_) = 0
//
// use_abs (_GENESIS2_INHERITANCE_PRIORITY_) = 1
//
// use_max_min (_GENESIS2_INHERITANCE_PRIORITY_) = 1
//
// use_relu (_GENESIS2_INHERITANCE_PRIORITY_) = 0
//
// en_opt (_GENESIS2_INHERITANCE_PRIORITY_) = 1
//
// en_trick (_GENESIS2_INHERITANCE_PRIORITY_) = 0
//
// en_ovfl (_GENESIS2_INHERITANCE_PRIORITY_) = 1
//
// is_msb (_GENESIS2_INHERITANCE_PRIORITY_) = 0
//
// en_double (_GENESIS2_INHERITANCE_PRIORITY_) = 0
//
// get_carry (_GENESIS2_INHERITANCE_PRIORITY_) = 1
//
// debug (_GENESIS2_INHERITANCE_PRIORITY_) = 0
//
// ADD PARAMETERIZATION HERE

/*
$use_add  = 1
*/


module   test_pe_comp_unq1 (
  input [7:0]                    op_code,

  input  [15:0]         op_a,
  input  [15:0]         op_b,
  input                          op_d_p,

  output logic [3 : 0]             carry_out,


  output logic [15:0]   res,
  output logic [3 : 0] ovfl,
  output logic [3 : 0]    res_p
);

localparam DATA_MSB      = 16 - 1;

localparam PE_ADD_OP     = 6'h0;

localparam PE_SUB_OP     = 6'h1;

localparam PE_ABS_OP     = 6'h3;

localparam PE_GTE_MAX_OP = 6'h4;
localparam PE_LTE_MIN_OP = 6'h5;


localparam PE_SEL_OP     = 6'h8;

localparam PE_RSHFT_OP   = 6'hF;
localparam PE_LSHFT_OP   = 6'h11;

localparam PE_MULT_0_OP  = 6'hB;
localparam PE_MULT_1_OP  = 6'hC;
localparam PE_MULT_2_OP  = 6'hD;

localparam PE_OR_OP      = 6'h12;
localparam PE_AND_OP     = 6'h13;
localparam PE_XOR_OP     = 6'h14;


//ADD PERL HERE IF NEED BE
localparam PE_ADD_VEC_OP= 6'h16;
localparam PE_SUB_VEC_OP= 6'h17;
localparam PE_MUL0_VEC4_OP=6'h1b;
localparam PE_MUL1_VEC4_OP=6'h1c;
localparam PE_MUL0_VEC2_OP=6'h2b;
localparam PE_MUL1_VEC2_OP=6'h2c;	


logic [31:0] mult_res;

logic [31:0] mult_res_v4;
logic [31:0] mult_res_v2;

logic [7:0]        nc_op_code;
assign             nc_op_code = op_code;


logic [DATA_MSB:0] res_w;
logic [3 : 0] res_p_w;

logic                 is_signed;
//logic                 dual_mode;

logic                 cmpr_lte;
logic                 cmpr_gte;
logic                 cmpr_eq;

localparam NUM_ADDERS = 1;
localparam ADD_MSB = NUM_ADDERS - 1;
localparam NUM_SEGS = 4;

logic [DATA_MSB:0]   add_a     [ADD_MSB:0];
logic [DATA_MSB:0]   add_b     [ADD_MSB:0];
logic                add_c_in  [ADD_MSB:0];

wire  [DATA_MSB:0]   add_res   [ADD_MSB:0];
wire  [NUM_SEGS-1:0] add_c_out [ADD_MSB:0];

//temporary: logic for holding vector multiply signs
logic [3:0] vec4_cout;
logic [1:0] vec2_cout;
//genvar ggg;
logic is_addsub_vec;
assign is_addsub_vec = (op_code[5:0] == PE_ADD_VEC_OP) || (op_code[5:0] == PE_SUB_VEC_OP);

//removing generative two-add stuff for now

test_full_add #(.DataWidth(16)) full_add
  (
    .a     (add_a[0]),
    .b     (add_b[0]),
    .c_in  (add_c_in[0]),
    .is_vec (is_addsub_vec),

//      .dual_mode (dual_mode),

    .res   (add_res[0]),
    .c_out (add_c_out[0])
  );

  assign carry_out = is_addsub_vec? add_c_out[0] : {{add_c_out[0][3]}, {3{1'b0}}};

genvar vec4_mul_gen;
genvar vec2_mul_gen;
generate
  for(vec4_mul_gen=1;vec4_mul_gen<5;vec4_mul_gen=vec4_mul_gen+1) begin : GEN_VEC4_MUL
  test_mult_add #(.DataWidth(16/4)) mult_add_v4
    (
      .a     (op_a[(16/4)*(vec4_mul_gen)-1:(16/4)*(vec4_mul_gen-1)]),
      .b     (op_b[(16/4)*(vec4_mul_gen)-1:(16/4)*(vec4_mul_gen-1)]),
//  .dual_mode(dual_mode),
      .res   (mult_res_v4[(16/2)*(vec4_mul_gen)-1:(16/2)*(vec4_mul_gen-1)]),
      .c_out (vec4_cout[vec4_mul_gen-1])
    );
  end
endgenerate
generate
  for(vec2_mul_gen=1;vec2_mul_gen<3;vec2_mul_gen=vec2_mul_gen+1) begin : GEN_VEC2_MUL
  test_mult_add #(.DataWidth(16/2)) mult_add_v2
    (
      .a     (op_a[(16/2)*(vec2_mul_gen)-1:(16/2)*(vec2_mul_gen-1)]),
      .b     (op_b[(16/2)*(vec2_mul_gen)-1:(16/2)*(vec2_mul_gen-1)]),
//  .dual_mode(dual_mode),
      .res   (mult_res_v2[(16)*(vec2_mul_gen)-1:(16)*(vec2_mul_gen-1)]),
      .c_out (vec2_cout[vec2_mul_gen-1])
    );
  end
endgenerate
assign cmpr_eq   =  ~|(op_a ^ op_b);



test_cmpr  cmpr
(
  .a_msb     (op_a[DATA_MSB]),
  .b_msb     (op_b[DATA_MSB]),
  .diff_msb  (add_res[0][DATA_MSB]),
  .is_signed (is_signed),
  .eq        (cmpr_eq),

  .lte       (cmpr_lte),
  .gte       (cmpr_gte)
);



logic                 mult_c_out;

test_mult_add #(.DataWidth(16)) test_mult_add
(
  .is_signed (is_signed),

  .a  (op_a),
  .b  (op_b),

//  .dual_mode(dual_mode),

  .res   (mult_res),
  .c_out (mult_c_out)
);




logic [DATA_MSB:0] shift_res;

test_shifter_unq1 #(.DataWidth(16)) test_shifter
(
  .is_signed (is_signed),
  .dir_left(op_code[5:0]==PE_LSHFT_OP),

  .a  (op_a),
  .b   (op_b[$clog2(16)-1+0:0]),

  .res (shift_res)
);


assign is_signed   = op_code[6];
//assign dual_mode   = op_code[8]; //Save the OP code bit for half precision support


logic diff_sign;
assign diff_sign = add_res[0][DATA_MSB];


localparam DataMSB = 16-1;
logic [ADD_MSB:0] ovfl_add_signed;

assign ovfl_add_signed[0] = (op_a[DataMSB] == op_b[DataMSB]) &
                            (op_a[DataMSB] != add_res[0][DataMSB]);

logic  ovfl_sub_signed;
always_comb begin
  ovfl_sub_signed = ((op_a[DataMSB] != op_b[DataMSB]) & (op_a[DataMSB] != add_res[0][DataMSB]));
end


always_comb begin : proc_alu
  add_a[0] = op_a;
  add_b[0] = op_b;
  add_c_in[0] = 1'b0;


  res_w   = add_res[ADD_MSB];
  res_p_w = add_c_out[ADD_MSB];

  ovfl = {4{1'b0}};


  unique case (op_code[5:0])
    PE_ADD_OP: begin
        add_c_in[0] = op_d_p;
        res_p_w     = add_c_out[0];
        ovfl        = {{(is_signed) ? (|ovfl_add_signed) : res_p_w[3]},{3{1'b0}}};
      end
    PE_SUB_OP: begin
        add_b[0]    = ~op_b;
        add_c_in[0] = 1'b1;
        ovfl        = {{(is_signed) ? ovfl_sub_signed : 1'b0},{3{1'b0}}};
      end
    PE_ABS_OP: begin
        add_a[0]    = ~op_a;
        add_b[0]    = 0;
        add_c_in[0] = 1'b1;
        res_p_w     = {{op_a[DATA_MSB]},{3{1'b0}}};

        res_w       = (diff_sign | !is_signed) ? op_a : add_res[0];
        ovfl        = {{res_w[DATA_MSB]},{3{1'b0}}};

    end

    PE_GTE_MAX_OP: begin
        add_b[0]    = ~op_b;
        add_c_in[0] = 1'b1;
        res_p_w     = {{cmpr_gte},{3{1'b0}}};
        res_w       = res_p_w[3] ? op_a : op_b;
      end
    PE_LTE_MIN_OP: begin
        add_b[0]    = ~op_b;
        add_c_in[0] = 1'b1;
        res_p_w     = {{cmpr_lte},{3{1'b0}}};
        res_w       = res_p_w[3] ? op_a : op_b;
      end
      PE_SEL_OP: begin
        res_w = op_d_p ? op_a : op_b;
      end
    PE_RSHFT_OP: begin
        res_w = shift_res;
      end
    PE_LSHFT_OP: begin
        res_w = shift_res;
      end
    PE_MULT_0_OP: begin
        res_w   = mult_res[DATA_MSB:0];
        res_p_w = {{mult_c_out},{3{1'b0}}};
        if (is_signed) begin
          ovfl = {{(op_a[DATA_MSB] == op_b[DATA_MSB]) ?
                                    mult_res[DATA_MSB] :
                                    ~mult_res[DATA_MSB] & |{op_a, op_b}},{3{1'b0}}};
        end else begin
          ovfl = {{|mult_res[31:16]},{3{1'b0}}};
        end
      end
    PE_MULT_1_OP: begin
        res_w   = mult_res[23:8];
        res_p_w = {{mult_c_out},{3{1'b0}}};
        if (is_signed) begin
          ovfl = {{(op_a[DATA_MSB] == op_b[DATA_MSB]) ?
                                    mult_res[DATA_MSB] :
                                    ~mult_res[DATA_MSB] & |{op_a, op_b}},{3{1'b0}}};
        end else begin
          ovfl = {{|mult_res[31:24]},{3{1'b0}}};
        end
      end
    PE_MULT_2_OP: begin
        res_w   = mult_res[31:16];
        res_p_w = {{mult_c_out},{3{1'b0}}};
        ovfl = {{1'b0},{3{1'b0}}};
      end


    PE_OR_OP: begin
        res_w = op_a | op_b;
      end
    PE_AND_OP: begin
        res_w = op_a & op_b;
      end
    PE_XOR_OP: begin
        res_w = op_a ^ op_b;
      end


    PE_ADD_VEC_OP: begin
      res_p_w = add_c_out[0] ;
      add_c_in[0] = 1'b0;
      //parameterize overflow better!
      ovfl = is_signed ? {(op_a[15] == op_b[15]) &
                           (op_a[15] != add_res[0][15]),
                           (op_a[11] == op_b[11]) &
                           (op_a[11] != add_res[0][11]),
                           (op_a[7] == op_b[7]) &
                           (op_a[7] != add_res[0][7]),
                           (op_a[3] == op_b[3]) &
                           (op_a[3] != add_res[0][3])
                           } : res_p_w ;
    end

    PE_SUB_VEC_OP: begin
      add_b[0]    = ~op_b;
      add_c_in[0] = 1'b1;
      res_p_w = add_c_out[0] ;
      //parameterize overflow better!
      ovfl = is_signed ? {(op_a[15] != op_b[15]) &
                     (op_a[15] != add_res[0][15]),
                     (op_a[11] != op_b[11]) &
                     (op_a[11] != add_res[0][11]),
                     (op_a[7] != op_b[7]) &
                     (op_a[7] != add_res[0][7]),
                     (op_a[3] != op_b[3]) &
                     (op_a[3] != add_res[0][3])
                     } : res_p_w ;
    end
	PE_MUL0_VEC4_OP: begin
        res_w   = {mult_res_v4[7*(16/4)-1:6*(16/4)], 
 				   mult_res_v4[5*(16/4)-1:4*(16/4)],
 				   mult_res_v4[3*(16/4)-1:2*(16/4)], 
				   mult_res_v4[(16/4)-1:0]};
        res_p_w = 4'b0;
		ovfl = 4'b0;
    end
	PE_MUL1_VEC4_OP: begin
        res_w   = {mult_res_v4[8*(16/4)-1:7*(16/4)], 
 				   mult_res_v4[6*(16/4)-1:5*(16/4)],
 				   mult_res_v4[4*(16/4)-1:3*(16/4)], 
				   mult_res_v4[2*(16/4)-1:(16/4)]};
        res_p_w = 1'b0;
		ovfl = 4'b0;
	end
	PE_MUL0_VEC2_OP: begin
        res_w   = {mult_res_v2[3*(16/2)-1:2*(16/2)], 
 				   mult_res_v2[(16/2)-1:0]};
        res_p_w = 4'b0;
		ovfl = 4'b0;
	end
	PE_MUL1_VEC2_OP: begin
        res_w   = {mult_res_v2[4*(16/2)-1:3*(16/2)], 
 				   mult_res_v2[2*(16/2)-1:(16/2)]};
        res_p_w = 4'b0;
		ovfl = 4'b0;
	end
    default: begin
        res_w   = op_a;
        res_p_w = {{op_d_p},{3{1'b0}}};
      end
  endcase
end


assign res   = res_w;
assign res_p = res_p_w;

endmodule
