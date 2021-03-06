import magma
import mantle
import generator.generator as generator
from simple_sb.simple_sb_magma import SB
from simple_cb.simple_cb_magma import CB
from common.side_type import SideType
from generator.configurable import ConfigurationType
from generator.from_magma import FromMagma
from common.mux_with_default import MuxWithDefaultWrapper


def get_width(T):
    if isinstance(T, magma._BitKind):
        return 1
    if isinstance(T, magma.BitsKind):
        return T.N
    raise NotImplementedError(T, type(T))


class Tile(generator.Generator):
    def __init__(self, core):
        super().__init__()

        self.core = core
        self.sb = SB(self.core.outputs())
        widths = [get_width(i.type()) for i in self.core.inputs()]
        self.cbs = [CB(10, w) for w in widths]

        self.add_ports(
            north=SideType(5, (1, 16)),
            west=SideType(5, (1, 16)),
            south=SideType(5, (1, 16)),
            east=SideType(5, (1, 16)),
            config=magma.In(ConfigurationType(32, 32)),
            tile_id=magma.In(magma.Bits(16)),
            clk=magma.In(magma.Clock),
            reset=magma.In(magma.AsyncReset),
            read_config_data=magma.Out(magma.Bits(32)),
            stall=magma.In(magma.Bits(4))
        )

        self.wire(self.ports.north, self.sb.ports.north)
        self.wire(self.ports.west, self.sb.ports.west)
        self.wire(self.ports.south, self.sb.ports.south)
        self.wire(self.ports.east, self.sb.ports.east)

        # this is hacky, but connect stall if the core has a stall input
        if "stall" in self.core.ports:
            self.wire(self.ports.stall, core.ports.stall)

        sides = (self.ports.north, self.ports.west)
        for i, cb in enumerate(self.cbs):
            side = sides[i % len(sides)]
            self.__wire_cb(side, cb)

        for i, input_ in enumerate(self.core.inputs()):
            self.wire(self.cbs[i].ports.O, input_)

        for i, out in enumerate(self.core.outputs()):
            self.wire(out, self.sb.ports[out._name])

        for feature in self.features():
            self.wire(self.ports.config.config_addr[24:32],
                      feature.ports.config.config_addr)
            self.wire(self.ports.config.config_data,
                      feature.ports.config.config_data)
            self.wire(self.ports.config.read, feature.ports.config.read)

        # read_data mux
        num_mux_inputs = len(self.features())
        self.read_data_mux = MuxWithDefaultWrapper(num_mux_inputs, 32, 8, 0)

        # Connect S input to config_addr.feature.
        self.wire(self.ports.config.config_addr[16:24],
                  self.read_data_mux.ports.S)
        self.wire(self.read_data_mux.ports.O, self.ports.read_config_data)

        # Logic to generate EN input for read_data_mux
        self.read_and_tile = FromMagma(mantle.DefineAnd(2))
        self.eq_tile = FromMagma(mantle.DefineEQ(16))
        # config_addr.tile_id == self.tile_id?
        self.wire(self.ports.tile_id, self.eq_tile.ports.I0)
        self.wire(self.ports.config.config_addr[0:16], self.eq_tile.ports.I1)
        # (config_addr.tile_id == self.tile_id) & READ
        self.wire(self.read_and_tile.ports.I0, self.eq_tile.ports.O)
        self.wire(self.read_and_tile.ports.I1, self.ports.config.read[0])
        # read_data_mux.EN = (config_addr.tile_id == self.tile_id) & READ
        self.wire(self.read_and_tile.ports.O, self.read_data_mux.ports.EN[0])

        # Logic for writing to config registers
        # Config_en_tile = (config_addr.tile_id == self.tile_id & WRITE)
        self.write_and_tile = FromMagma(mantle.DefineAnd(2))
        self.wire(self.write_and_tile.ports.I0, self.eq_tile.ports.O)
        self.wire(self.write_and_tile.ports.I1, self.ports.config.write[0])
        self.decode_feat = []
        self.feat_and_config_en_tile = []
        for i, feat in enumerate(self.features()):
            # wire each feature's read_data output to
            # read_data_mux inputs
            self.wire(feat.ports.read_config_data,
                      self.read_data_mux.ports.I[i])
            # for each feature,
            # config_en = (config_addr.feature == feature_num) & config_en_tile
            self.decode_feat.append(FromMagma(mantle.DefineDecode(i, 8)))
            self.feat_and_config_en_tile.append(FromMagma(mantle.DefineAnd(2)))
            self.wire(self.decode_feat[i].ports.I,
                      self.ports.config.config_addr[16:24])
            self.wire(self.decode_feat[i].ports.O,
                      self.feat_and_config_en_tile[i].ports.I0)
            self.wire(self.write_and_tile.ports.O,
                      self.feat_and_config_en_tile[i].ports.I1)
            self.wire(self.feat_and_config_en_tile[i].ports.O,
                      feat.ports.config.write[0])

    def __wire_cb(self, side, cb):
        if cb.width == 1:
            self.wire(side.I.layer1, cb.ports.I[:5])
            # TODO(rsetaluri): Use anonymous ports instead.
            self.wire(self.sb.ports[side._name].O.layer1, cb.ports.I[5:])
        elif cb.width == 16:
            self.wire(side.I.layer16, cb.ports.I[:5])
            # TODO(rsetaluri): Use anonymous ports instead.
            self.wire(self.sb.ports[side._name].O.layer16, cb.ports.I[5:])
        else:
            raise NotImplementedError(cb, cb.width)

    # Takes in an existing input of the tile and creates and output
    # to pass the signal through
    # returns the new output port reference
    def pass_signal_through(self, signal):
        if signal in self.ports.values():
            pass_through = signal
        elif signal in self.ports.keys():
            pass_through = self.ports[signal]
        # Create output port for pass through
        output_name = pass_through.qualified_name() + "_out"
        self.add_port(output_name, magma.Out(pass_through.base_type()))
        # Actually make the pass through connection
        self.wire(pass_through, self.ports[output_name])
        return self.ports[output_name]

    # Embeds read_data reduction network in tile by accepting a read_data
    # input from another tile and ORing it with the origin read_data
    # output of this tile to create a new read_data output
    # TODO: Make some more generally useful form of this transformation
    def read_data_reduction(self):
        pass_through = self.ports.read_config_data
        input_name = pass_through.qualified_name() + "_in"
        # Create input port for pass through read_data reduction
        self.add_port(input_name, magma.In(pass_through.base_type()))
        # Remove the current connection to the read_data output
        self.remove_wire(self.read_data_mux.ports.O, pass_through)
        self.read_data_reduce_or = FromMagma(mantle.DefineOr(2, 32))
        # OR previous read_data output with read_data input to create NEW
        # read_data output
        self.wire(self.read_data_mux.ports.O,
                  self.read_data_reduce_or.ports.I0)
        self.wire(self.ports[input_name], self.read_data_reduce_or.ports.I1)
        self.wire(self.read_data_reduce_or.ports.O, pass_through)

    def features(self):
        return (self.core, self.sb, *(cb for cb in self.cbs))

    def name(self):
        return f"Tile_{self.core.name()}"
