"""
This is a layer build on top of Cyclone
"""
from common.core import Core
from common.mux_with_default import MuxWithDefaultWrapper
from common.zext_wrapper import ZextWrapper
from generator.configurable import Configurable, ConfigurationType
from .cyclone import Node, PortNode, Tile, SwitchBoxNode, SwitchBoxIO
from .cyclone import SwitchBox, InterconnectCore
import mantle
from common.mux_wrapper import MuxWrapper
import magma
from typing import Dict, Tuple, List
from abc import abstractmethod
import generator.generator as generator
from generator.from_magma import FromMagma


def create_name(name: str):
    tokens = " (),"
    for t in tokens:
        name = name.replace(t, "_")
    name = name.replace("__", "_")
    if name[-1] == "_":
        name = name[:-1]
    return name


def get_mux_sel_name(node: Node):
    return f"{create_name(str(node))}_sel"


def create_mux(node: Node):
    conn_in = node.get_conn_in()
    height = len(conn_in)
    mux = MuxWrapper(height, node.width)
    return mux


class InterconnectConfigurable(Configurable):
    def __init__(self, config_addr_width: int, config_data_width: int):
        super().__init__()
        self.config_addr_width = config_addr_width
        self.config_data_width = config_data_width

        self.read_config_data_mux: MuxWrapper = None

        # ports for reconfiguration
        self.add_ports(
            clk=magma.In(magma.Clock),
            reset=magma.In(magma.AsyncReset),
        )

    def _setup_config(self):
        # sort the registers by it's name. this will be the order of config
        # addr index
        config_names = list(self.registers.keys())
        config_names.sort()
        for idx, config_name in enumerate(config_names):
            reg = self.registers[config_name]
            # set the configuration registers
            reg.set_addr(idx)
            reg.set_addr_width(self.config_addr_width)
            reg.set_data_width(self.config_data_width)

            self.wire(self.ports.config.config_addr, reg.ports.config_addr)
            self.wire(self.ports.config.config_data, reg.ports.config_data)
            self.wire(self.ports.config.write[0], reg.ports.config_en)
            self.wire(self.ports.reset, reg.ports.reset)

        # read_config_data output
        num_config_reg = len(config_names)
        if num_config_reg > 1:
            self.read_config_data_mux = MuxWrapper(num_config_reg,
                                                   self.config_data_width)
            sel_bits = self.read_config_data_mux.sel_bits
            # Wire up config_addr to select input of read_data MUX
            self.wire(self.ports.config.config_addr[:sel_bits],
                      self.read_config_data_mux.ports.S)
            self.wire(self.read_config_data_mux.ports.O,
                      self.ports.read_config_data)

            for idx, config_name in enumerate(config_names):
                reg = self.registers[config_name]
                zext = ZextWrapper(reg.width, self.config_data_width)
                self.wire(reg.ports.O, zext.ports.I)
                zext_out = zext.ports.O
                self.wire(zext_out, self.read_config_data_mux.ports.I[idx])
        else:
            config_name = config_names[0]
            reg = self.registers[config_name]
            zext = ZextWrapper(reg.width, self.config_data_width)
            self.wire(reg.ports.O, zext.ports.I)
            zext_out = zext.ports.O
            self.wire(zext_out, self.ports.read_config_data)

    @abstractmethod
    def name(self):
        pass


class CB(InterconnectConfigurable):
    def __init__(self, node: PortNode,
                 config_addr_width: int, config_data_width: int):
        if not isinstance(node, PortNode):
            raise ValueError(node, PortNode.__name__)
        super().__init__(config_addr_width, config_data_width)

        self.node: PortNode = node
        self.mux = create_mux(self.node)

        # lift the port to the top level
        self.add_ports(
            I=self.mux.ports.I.base_type(),
            O=self.mux.ports.O.base_type())

        self.wire(self.ports.I, self.mux.ports.I)
        self.wire(self.ports.O, self.mux.ports.O)

        if self.mux.height > 1:
            self.add_ports(
                config=magma.In(ConfigurationType(config_addr_width,
                                                  config_data_width)),
                read_config_data=magma.Out(magma.Bits(config_data_width)),
            )
            config_name = get_mux_sel_name(self.node)
            self.add_config(config_name, self.mux.sel_bits)
            self.wire(self.registers[config_name].ports.O,
                      self.mux.ports.S)

        self._setup_config()

    def name(self):
        return create_name(str(self.node))


class SB(InterconnectConfigurable):
    def __init__(self, switchbox: SwitchBox, config_addr_width: int,
                 config_data_width: int):
        super().__init__(config_addr_width, config_data_width)
        self.switchbox = switchbox

        # lift the ports up
        sbs = self.switchbox.get_all_sbs()
        self.sb_muxs: Dict[str, Tuple[SwitchBoxNode, MuxWrapper]] = {}
        # first pass to create the mux circuit
        for sb in sbs:
            sb_name = str(sb)
            self.sb_muxs[sb_name] = (sb, create_mux(sb))
        # second pass to lift the ports and wire them

        for sb_name, (sb, mux) in self.sb_muxs.items():
            # only lift them if the ports are connect to the outside world
            port_name = create_name(sb_name)
            if sb.io == SwitchBoxIO.SB_IN:
                self.add_port(port_name, magma.In(mux.ports.I.base_type()))
                self.wire(self.ports[port_name], mux.ports.I)

            else:
                self.add_port(port_name, magma.Out(mux.ports.O.base_type()))
                self.wire(self.ports[port_name], mux.ports.O)

        # connect internal sbs
        self.__connect_sbs()

        # set up the configuration registers
        self.add_ports(
            config=magma.In(ConfigurationType(config_addr_width,
                                              config_data_width)),
            read_config_data=magma.Out(magma.Bits(config_data_width)),
        )
        for _, (sb, mux) in self.sb_muxs.items():
            config_name = get_mux_sel_name(sb)
            if mux.height > 1:
                assert mux.sel_bits > 0
                self.add_config(config_name, mux.sel_bits)
                self.wire(self.registers[config_name].ports.O,
                          mux.ports.S)

        self._setup_config()

    def name(self):
        return create_name(str(self.switchbox)) + \
            f"{self.switchbox.x}_{self.switchbox.y}"

    def __connect_sbs(self):
        # the principle is that it only connects to the nodes within
        # its range. for instance, in SB we only connect to sb nodes
        for _, (sb, mux) in self.sb_muxs.items():
            if sb.io == SwitchBoxIO.SB_IN:
                for node in sb:
                    if not isinstance(node, SwitchBoxNode):
                        continue
                    assert node.io == SwitchBoxIO.SB_OUT
                    assert node.x == sb.x and node.y == sb.y
                    output_port = mux.ports.O
                    idx = node.get_conn_in().index(sb)
                    node_, node_mux = self.sb_muxs[str(node)]
                    assert node_ == node
                    input_port = node_mux.ports.I[idx]
                    self.wire(input_port, output_port)


class TileCircuit(generator.Generator):
    """We merge tiles at the same coordinates with different bit widths
    The only requirements is that the tiles have to be on the same
    coordinates. Their heights do not have to match.

    We don't deal with stall signal here since it's not interconnect's job
    to handle that signal
    """
    def __init__(self, tiles: Dict[int, Tile],
                 config_addr_width: int, config_data_width: int,
                 tile_id_width: int = 16,
                 full_config_addr_width: int = 32):
        super().__init__()

        self.tiles = tiles
        self.config_addr_width = config_addr_width
        self.config_data_width = config_data_width
        self.tile_id_width = tile_id_width

        # compute config addr sizes
        # (16, 24)
        full_width = full_config_addr_width
        self.feature_addr_slice = slice(full_width - self.tile_id_width,
                                        full_width - self.config_addr_width)
        # (0, 16)
        self.tile_id_slice = slice(0, self.tile_id_width)
        # (24, 32)
        self.feature_config_slice = slice(full_width - self.config_addr_width,
                                          full_width)

        # sanity check
        x = -1
        y = -1
        core = None
        for bit_width, tile in self.tiles.items():
            assert bit_width == tile.track_width
            if x == -1:
                x = tile.x
                y = tile.y
                core = tile.core
            else:
                assert x == tile.x
                assert y == tile.y
                # the restriction is that all the tiles in the same coordinate
                # have to have the same core, otherwise it's physically
                # impossible
                assert core == tile.core

        assert x != -1 and y != -1
        self.x = x
        self.y = y
        self.core = core.core

        # create cb and switchbox
        self.cbs: Dict[str, CB] = {}
        self.sbs: Dict[int, SB] = {}
        # we only create cb if it's an input port, which doesn't have
        # graph neighbors
        for bit_width, tile in self.tiles.items():
            core = tile.core
            # connection box time
            for port_name, port_node in tile.ports.items():
                # input ports
                if len(port_node) == 0:
                    # make sure that it has at least one connection
                    assert len(port_node.get_conn_in()) > 0
                    assert bit_width == port_node.width

                    # create a CB
                    port_ref = core.get_port_ref(port_node.name)
                    cb = CB(port_node, config_addr_width, config_data_width)
                    self.wire(cb.ports.O, port_ref)
                    self.cbs[port_name] = cb
                else:
                    # output ports
                    assert len(port_node.get_conn_in()) == 0
                    assert bit_width == port_node.width

            # switch box time
            sb = SB(tile.switchbox, config_addr_width, config_data_width)
            self.sbs[sb.switchbox.width] = sb

        # lift all the sb ports up
        for _, switchbox in self.sbs.items():
            sbs = switchbox.switchbox.get_all_sbs()
            assert switchbox.switchbox.x == self.x
            assert switchbox.switchbox.y == self.y
            for sb in sbs:
                sb_name = create_name(str(sb))
                node, mux = switchbox.sb_muxs[str(sb)]
                assert node == sb
                assert sb.x == self.x
                assert sb.y == self.y
                port = switchbox.ports[sb_name]
                if node.io == SwitchBoxIO.SB_IN:
                    self.add_port(sb_name, magma.In(port.base_type()))
                    # FIXME:
                    #   it seems like I need this hack to by-pass coreIR's
                    #   checking, even though it's connected below
                    self.wire(self.ports[sb_name], mux.ports.I)
                else:
                    self.add_port(sb_name, magma.Out(port.base_type()))
                assert port.owner() == switchbox
                self.wire(self.ports[sb_name], port)

        # connect ports from cb to switch box and back
        for _, cb in self.cbs.items():
            conn_ins = cb.node.get_conn_in()
            for idx, node in enumerate(conn_ins):
                assert isinstance(node, SwitchBoxNode)
                assert node.x == self.x
                assert node.y == self.y
                bit_width = node.width
                sb_circuit = self.sbs[bit_width]
                if node.io == SwitchBoxIO.SB_IN:
                    # get the internal wire
                    n, sb_mux = sb_circuit.sb_muxs[str(node)]
                    assert n == node
                    self.wire(sb_mux.ports.O, cb.ports.I[idx])
                else:
                    sb_name = create_name(str(node))
                    self.wire(sb_circuit.ports[sb_name], cb.ports.I[idx])

        # connect ports from core to switch box
        for bit_width, tile in self.tiles.items():
            for _, port_node in tile.ports.items():
                if len(port_node) > 0:
                    assert len(port_node.get_conn_in()) == 0
                    port_name = port_node.name
                    for sb_node in port_node:
                        assert isinstance(sb_node, SwitchBoxNode)
                        assert sb_node.x == self.x
                        assert sb_node.y == self.y
                        idx = sb_node.get_conn_in().index(port_node)
                        sb_circuit = self.sbs[port_node.width]
                        # we need to find the actual mux
                        n, mux = sb_circuit.sb_muxs[str(sb_node)]
                        assert n == sb_node
                        # the generator doesn't allow circular reference
                        # we have to be very creative here
                        if port_name not in sb_circuit.ports:
                            sb_circuit.add_port(port_name,
                                                magma.In(magma.Bits(bit_width)))
                            self.wire(self.core.ports[port_name],
                                      sb_circuit.ports[port_name])
                        sb_circuit.wire(sb_circuit.ports[port_name],
                                        mux.ports.I[idx])

        # add configuration space
        # we can't use the InterconnectConfigurable because the tile class
        # doesn't have any mux
        self.__add_config()

    def __add_config(self):
        self.add_ports(
            config=magma.In(ConfigurationType(self.config_data_width,
                                              self.config_data_width)),
            tile_id=magma.In(magma.Bits(self.tile_id_width)),
            clk=magma.In(magma.Clock),
            reset=magma.In(magma.AsyncReset),
            read_config_data=magma.Out(magma.Bits(self.config_data_width)))

        features = self.features()
        num_features = len(features)
        self.read_data_mux = MuxWithDefaultWrapper(num_features,
                                                   self.config_data_width,
                                                   self.config_addr_width,
                                                   0)
        # most of the logic copied from tile_magma.py
        # remove all hardcoded values
        for feature in self.features():
            self.wire(self.ports.config.config_addr[self.feature_config_slice],
                      feature.ports.config.config_addr)
            self.wire(self.ports.config.config_data,
                      feature.ports.config.config_data)
            self.wire(self.ports.config.read, feature.ports.config.read)

        # Connect S input to config_addr.feature.
        self.wire(self.ports.config.config_addr[self.feature_addr_slice],
                  self.read_data_mux.ports.S)
        self.wire(self.read_data_mux.ports.O, self.ports.read_config_data)

        # Logic to generate EN input for read_data_mux
        self.read_and_tile = FromMagma(mantle.DefineAnd(2))
        self.eq_tile = FromMagma(mantle.DefineEQ(self.tile_id_width))
        # config_addr.tile_id == self.tile_id?
        self.wire(self.ports.tile_id, self.eq_tile.ports.I0)
        self.wire(self.ports.config.config_addr[self.tile_id_slice],
                  self.eq_tile.ports.I1)
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
            self.decode_feat.append(
                FromMagma(mantle.DefineDecode(i, self.config_addr_width)))
            self.feat_and_config_en_tile.append(FromMagma(mantle.DefineAnd(2)))
            self.wire(self.decode_feat[i].ports.I,
                      self.ports.config.config_addr[self.feature_addr_slice])
            self.wire(self.decode_feat[i].ports.O,
                      self.feat_and_config_en_tile[i].ports.I0)
            self.wire(self.write_and_tile.ports.O,
                      self.feat_and_config_en_tile[i].ports.I1)
            self.wire(self.feat_and_config_en_tile[i].ports.O,
                      feat.ports.config.write[0])

    def features(self) -> List[generator.Generator]:
        cb_names = list(self.cbs.keys())
        cb_names.sort()
        cb_features = [self.cbs[name] for name in cb_names]
        sb_widths = list(self.sbs.keys())
        sb_widths.sort()
        sb_features = [self.sbs[width] for width in sb_widths]
        return [self.core] + cb_features + sb_features

    def get_route_bitstream_config(self, src_node: Node, dst_node: Node):
        assert src_node.width == dst_node.width
        tile = self.tiles[src_node.width]
        assert dst_node.x == tile.x and dst_node.y == tile.y,\
            f"{dst_node} is not in {tile}"
        assert dst_node in src_node,\
            f"{dst_node} is not connected to {src_node}"

        config_data = dst_node.get_conn_in().index(src_node)
        # find the circuit
        if isinstance(dst_node, SwitchBoxNode):
            circuit = self.sbs[src_node.width]
        elif isinstance(dst_node, PortNode):
            circuit = self.cbs[dst_node.name]
        else:
            raise NotImplementedError(type(dst_node))
        reg_index = self.__find_reg_index(circuit, dst_node)
        feature_addr = self.features().index(circuit)
        # construct the addr and data
        addr = (reg_index << self.feature_config_slice.start) | \
               (feature_addr << self.tile_id_width)
        return addr, config_data

    @staticmethod
    def __find_reg_index(circuit: InterconnectConfigurable, node: Node):
        config_names = list(circuit.registers.keys())
        config_names.sort()
        mux_sel_name = get_mux_sel_name(node)
        return config_names.index(mux_sel_name)

    def name(self):
        return create_name(f"TILE {self.x} {self.y}")


class CoreInterface(InterconnectCore):
    def __init__(self, core: Core):
        super().__init__()

        self.input_ports = {}
        self.output_ports = {}

        self.core: Core = core

        for port in core.inputs():
            port_name = port.qualified_name()
            width = self.__get_bit_width(port)
            self.input_ports[port_name] = (width, port)

        for port in core.outputs():
            port_name = port.qualified_name()
            width = self.__get_bit_width(port)
            self.output_ports[port_name] = (width, port)

    def inputs(self):
        return [(width, name) for name, (width, _) in self.input_ports.items()]

    def outputs(self):
        return [(width, name) for name, (width, _) in self.output_ports.items()]

    def get_port_ref(self, port_name: str):
        if port_name in self.input_ports:
            return self.input_ports[port_name][1]
        else:
            return self.output_ports[port_name][1]

    @staticmethod
    def __get_bit_width(port):
        # nasty function to get the actual bit width from the port reference
        t = port.type()
        if isinstance(t, magma.BitKind):
            return 1
        if isinstance(port.type(), magma.BitsKind):
            return len(t)
        raise NotImplementedError(t, type(t))

    def __eq__(self, other: "CoreInterface"):
        return other.core == self.core
