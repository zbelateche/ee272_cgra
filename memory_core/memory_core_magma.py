import magma
import mantle
from generator.configurable import ConfigurationType
from common.core import Core
from common.coreir_wrap import CoreirWrap
from generator.const import Const
from generator.from_magma import FromMagma
from generator.from_verilog import FromVerilog
from memory_core import memory_core_genesis2


class MemCore(Core):
    def __init__(self, data_width, data_depth):
        super().__init__()

        self.data_width = data_width
        self.data_depth = data_depth
        TData = magma.Bits(self.data_width)
        TBit = magma.Bits(1)

        self.add_ports(
            data_in=magma.In(TData),
            addr_in=magma.In(TData),
            data_out=magma.Out(TData),
            clk=magma.In(magma.Clock),
            config=magma.In(ConfigurationType(8, 32)),
            read_config_data=magma.Out(magma.Bits(32)),
            reset=magma.In(magma.AsyncReset),
            flush=magma.In(TBit),
            wen_in=magma.In(TBit),
            ren_in=magma.In(TBit),
            stall=magma.In(magma.Bits(4))
        )

        wrapper = memory_core_genesis2.memory_core_wrapper
        param_mapping = memory_core_genesis2.param_mapping
        generator = wrapper.generator(param_mapping, mode="declare")
        circ = generator(data_width=self.data_width,
                         data_depth=self.data_depth)
        self.underlying = FromMagma(circ)

        self.wire(self.ports.data_in, self.underlying.ports.data_in)
        self.wire(self.ports.addr_in, self.underlying.ports.addr_in)
        self.wire(self.ports.data_out, self.underlying.ports.data_out)
        self.wire(self.ports.config.config_addr,
                  self.underlying.ports.config_addr[24:32])
        self.wire(self.ports.config.config_data,
                  self.underlying.ports.config_data)
        self.wire(self.ports.config.write[0], self.underlying.ports.config_en)
        self.wire(self.underlying.ports.read_data, self.ports.read_config_data)
        self.wire(self.ports.reset, self.underlying.ports.reset)
        self.wire(self.ports.flush[0], self.underlying.ports.flush)
        self.wire(self.ports.wen_in[0], self.underlying.ports.wen_in)
        self.wire(self.ports.ren_in[0], self.underlying.ports.ren_in)

        # PE core uses clk_en (essentially active low stall)
        self.stallInverter = FromMagma(mantle.DefineInvert(1))
        self.wire(self.stallInverter.ports.I, self.ports.stall[0:1])
        self.wire(self.stallInverter.ports.O[0], self.underlying.ports.clk_en)

        # TODO(rsetaluri): Actually wire these inputs.
        signals = (
            ("config_en_sram", 4),
            ("config_en_linebuf", 1),
            ("chain_wen_in", 1),
            ("config_read", 1),
            ("config_write", 1),
            ("chain_in", self.data_width),
        )
        for name, width in signals:
            val = magma.bits(0, width) if width > 1 else magma.bit(0)
            self.wire(Const(val), self.underlying.ports[name])
        self.wire(Const(magma.bits(0, 24)),
                  self.underlying.ports.config_addr[0:24])

    def inputs(self):
        return [self.ports.data_in, self.ports.addr_in, self.ports.flush,
                self.ports.ren_in, self.ports.wen_in]

    def outputs(self):
        return [self.ports.data_out]

    def name(self):
        return "MemCore"
