import math
from bit_vector import BitVector
import fault


def gen_cb(width: int,
           num_tracks: int,
           feedthrough_outputs: str,
           has_constant: bool,
           default_value: int):
    CONFIG_ADDR_WIDTH = 32
    CONFIG_DATA_WIDTH = 32
    # The names of the inputs to the module are given by @feedthrough_outputs.
    inputs = ["in_" + str(i)
              for i, c in enumerate(feedthrough_outputs) if c == "1"]
    # The number of total config bits needed is the number of bits needed to
    # select between all the inputs (including the constant if it is included),
    # as well as a constant value if @has_constant is True. Consequently, the
    # number of config registers needed is the total number of config bits
    # needed, divided by the size of a single config data element (e.g. 32
    # bits).
    mux_height = len(inputs)
    if has_constant:
        mux_height += 1
    mux_sel_bits = math.ceil(math.log(mux_height, 2))
    config_bits_needed = mux_sel_bits
    if has_constant:
        config_bits_needed += width
    num_config_regs = math.ceil(config_bits_needed / CONFIG_DATA_WIDTH)

    reset_val = num_tracks - feedthrough_outputs.count("0") + has_constant - 1
    reset_val = BitVector(reset_val, mux_sel_bits)
    if has_constant:
        reset_val = BitVector.concat(BitVector(default_value, width),
                                     reset_val)
    reset_val = BitVector(reset_val, CONFIG_DATA_WIDTH)

    class _CB:
        def __init__(self):
            self.__config = [BitVector(0, CONFIG_DATA_WIDTH)
                             for _ in range(num_config_regs)]
            self.reset()

        def reset(self):
            self.configure(BitVector(0, CONFIG_ADDR_WIDTH), reset_val)

            self.out = fault.UnknownValue
            self.read_data = fault.UnknownValue

        def configure(self, addr: BitVector, data: BitVector):
            assert addr.num_bits == CONFIG_ADDR_WIDTH
            assert data.num_bits == CONFIG_ADDR_WIDTH
            addr_high_bits = addr[24:32]
            config_reg_select = addr_high_bits.as_uint()
            if config_reg_select in range(num_config_regs):
                self.__config[config_reg_select] = data

        # Function to slice the global config bit space. Returns bits in the
        # range [lo, hi).
        def __get_config_bits(self, lo: int, hi: int):
            assert hi > lo
            assert lo >= 0
            assert hi <= (len(self.__config) * CONFIG_DATA_WIDTH)
            start = math.floor(lo / 32)
            end = math.floor((hi - 1) / 32)
            lo_int = lo % CONFIG_DATA_WIDTH
            hi_int = hi % CONFIG_DATA_WIDTH
            if start == end:
                return self.__config[start][lo_int:hi_int]
            ret = self.__config[start][lo_int:CONFIG_DATA_WIDTH]
            for i in range(start + 1, end):
                ret = BitVector.concat(ret, self.__config[i])
            ret = BitVector.concat(ret, self.__config[i][0:hi_int])
            assert ret.num_bits == (hi - lo)
            return ret

        def __call__(self, *args):
            assert len(args) == len(inputs)
            select = self.__get_config_bits(0, mux_sel_bits)
            select_as_uint = select.as_uint()
            # TODO: read_data logic
            if select_as_uint in range(len(inputs)):
                self.out = args[select_as_uint]
                return self.out
            if has_constant:
                return self.__get_config_bits(mux_sel_bits,
                                              mux_sel_bits + width)
            else:
                return BitVector(0, width)

        # Debug method to read config data.
        @property
        def config(self):
            return self.__config

    return _CB
