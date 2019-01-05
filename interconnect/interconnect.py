import enum
import abc
import generator.generator as generator
from common.core import Core
from typing import Union, Tuple, NamedTuple, List, Dict
from .cyclone import SwitchBoxSide, SwitchBoxIO, Graph, Tile as GTile
from .circuit import CB, EmptyCircuit, Connectable, SwitchBoxMux
from .tile_circiut import TileCircuit

GridCoordinate = Tuple[int, int]


class InterconnectType(enum.Enum):
    Mesh = 0
    Hierarchical = 1
    Hybrid = 2


# garnet's PEP 8 doesn't like the new way to declare named tuple with type
# hints using the old format
SBConnectionType = NamedTuple("SBConnectionType",
                              [("side", SwitchBoxSide),
                               ("track", int),
                               ("io", SwitchBoxIO)])


class InterconnectPolicy(enum.Enum):
    PassThrough = enum.auto()
    Ignore = enum.auto()


class InterConnectABC(generator.Generator):
    def __init__(self, track_width: int, connection_type: InterconnectType):
        super().__init__()
        self.track_width = track_width
        self.connection_type = connection_type

    @abc.abstractmethod
    def get_size(self):
        pass

    @abc.abstractmethod
    def add_tile(self, tile: TileCircuit):
        pass

    @abc.abstractmethod
    def get_tile(self, x: int, y: int):
        pass

    @abc.abstractmethod
    def realize(self) -> Dict[Tuple[int, int], List[generator.Generator]]:
        pass

    @abc.abstractmethod
    def set_core(self, x: int, y: int, core: Core):
        pass

    @abc.abstractmethod
    def connect(self, circuit_from: Connectable, circuit_to: Connectable):
        pass

    @abc.abstractmethod
    def disconnect(self, circuit_from: Connectable, circuit_to: Connectable):
        pass

    @abc.abstractmethod
    def is_connected(self, circuit_from: Connectable,
                     circuit_to: Connectable) -> bool:
        pass

    @abc.abstractmethod
    def dump_routing_graph(self, filename: str):
        pass

    @abc.abstractmethod
    def name(self):
        pass


class Interconnect(InterConnectABC):
    """This is the `traditional` sense of interconnect that doesn't deal with
    the global signals and clocks (since VPR doesnt do PnR on these signals
    either). We need a separate pass to produce global signals.
    The interconnect allows user to specify:
        1. Connection types for each port, i.e. SB (partly) and CB.
        2. Intra-connection types for each switch box, i.e. internal population
        3. Inter-connection types for switch box:
            a. variable length
            b. non-uniform routing resource
    """
    def __init__(self, track_width: int, connection_type: InterconnectType):
        super().__init__(track_width, connection_type)

        if connection_type != InterconnectType.Mesh:
            raise NotImplementedError("Only Mesh network is currently "
                                      "supported")
        self.__graph = Graph()

        # this is a 2d grid consistent with the routing graph. it's designed
        # to support fast query with irregular tile height.
        self.__grid: List[List[Union[TileCircuit, None]]] = []

        # Note (keyi):
        # notice that these following statement will trigger garnet's travis
        # to report E701 error. However, it is allowed in the updated
        # pycodestyle and pyflakes. It is because the PEP8 checker used in
        # garnet is about 4 years old and deprecated long time ago.
        # I'd personally suggest to switch to more modern style checker.
        # I will continue to use such type hints because that's the only way
        # to do so.

        # placeholders for sb and cb

        self.tiles: Dict[Tuple[int, int], TileCircuit] = {}

    def add_tile(self, tile: Union[TileCircuit, GTile]) -> None:
        if isinstance(tile, GTile):
            tile = TileCircuit(tile)
        self.__graph.add_tile(tile.g_tile)
        # adjusting grid_
        x = tile.x
        y = tile.y
        height = tile.height
        # automatically scale the chip
        while len(self.__grid) < y + height:
            self.__grid.append([])
        for row in range(len(self.__grid)):
            while len(self.__grid[row]) <= x:
                self.__grid[row].append(None)
        # store indices and checking for correctness
        self.__assign_grid(x, y, tile)
        for i in range(y + 1, y + height):
            # adding reference to that tile
            self.__assign_grid(x, i, tile)

    def get_tile(self, x: int, y: int) -> Union[TileCircuit, None]:
        width, height = self.get_size()
        if x >= width or y >= height:
            return None
        result = self.__grid[y][x]
        return result

    def __is_original_tile(self, x: int, y: int):
        tile = self.get_tile(x, y)
        return tile is not None and tile.x == x and tile.y == y

    def has_empty_tile(self) -> bool:
        for y in range(len(self.__grid)):
            for x in range(len(self.__grid[y])):
                if self.__grid[y][x] is None:
                    return True
        return False

    def __assign_grid(self, x: int, y: int,
                      tile: TileCircuit) -> None:
        if not isinstance(tile, TileCircuit):
            raise ValueError(tile, TileCircuit.__name__)
        self.__check_grid(x, y)
        self.__grid[y][x] = tile

    def __check_grid(self, x: int, y: int) -> None:
        if self.__grid[y][x] is not None:
            tile_index = self.__grid[y][x]
            tile_name = tile_index.name()
            raise RuntimeError(f"Tile ({x}, {y}) is assigned with " +
                               tile_name)

    def get_size(self) -> Tuple[int, int]:
        height = len(self.__grid)
        width = len(self.__grid[0])
        return width, height

    def set_core(self, x: int, y: int, core: Core):
        tile = self.get_tile(x, y)
        tile.set_core(core)

    def set_core_connection(self, x: int, y: int, port_name: str,
                            connection_type: List[SBConnectionType]):
        # we add a new port here
        tile_circuit = self.get_tile(x, y)
        # make sure that it's an input port
        is_input = tile_circuit.g_tile.core_has_input(port_name)
        is_output = tile_circuit.g_tile.core_has_output(port_name)

        if not is_input and not is_output:
            # the core doesn't have that port_name
            return
        elif not (is_input ^ is_output):
            raise ValueError("core design error. " + port_name + " cannot be "
                             " both input and output port")

        port_node = self.get_port_circuit(tile_circuit.x, tile_circuit.y,
                                          port_name)
        # add to graph node first, we will handle magma in a different pass
        # based on the graph, since we need to compute the mux height
        for side, track, io in connection_type:
            sb = self.get_sb_circuit(tile_circuit.x, tile_circuit.y, side,
                                     track, io)
            if is_input:
                self.connect(sb, port_node)
            else:
                self.connect(port_node, sb)

    def set_core_connection_all(self, port_name: str,
                                connection_type: List[Tuple[SwitchBoxSide,
                                                            SwitchBoxIO]]):
        """helper function to set connections for all the tiles with the
        same port_name"""
        width, height = self.get_size()
        visited = set()
        for y in range(height):
            for x in range(width):
                tile = self.__grid[y][x]
                if tile is not None and (tile.x, tile.y) not in visited:
                    # construct the connection types
                    switch = tile.switchbox.g_switch
                    num_track = switch.num_track
                    connections: List[SBConnectionType] = []
                    for track in range(num_track):
                        for side, io in connection_type:
                            connections.append(SBConnectionType(side, track,
                                                                io))
                    self.set_core_connection(x, y, port_name, connections)

                    # add it to visited
                    visited.add((tile.x, tile.y))

    def connect(self, circuit_from: Connectable, circuit_to: Connectable):
        # making sure that node to and from are indeed from the
        # interconnect circuit
        assert self.__is_part_of(circuit_from)
        assert self.__is_part_of(circuit_to)
        circuit_from.connect(circuit_to)

    def disconnect(self, circuit_from: Connectable, circuit_to: Connectable):
        assert self.__is_part_of(circuit_from)
        assert self.__is_part_of(circuit_to)
        circuit_from.disconnect(circuit_to)

    def is_connected(self, circuit_from: Connectable,
                     circuit_to: Connectable):
        if not self.__is_part_of(circuit_from) or \
                not self.__is_part_of(circuit_to):
            return False
        return circuit_from.is_connected(circuit_to)

    def __is_part_of(self, circuit: Connectable) -> bool:
        if not isinstance(circuit, Connectable):
            raise ValueError(circuit, Connectable.__name__)
        node = circuit.node
        track = node.track
        x = node.x
        y = node.y
        tile = self.get_tile(x, y)
        if isinstance(circuit, SwitchBoxMux):
            side = node.side
            io = node.io
            if tile is not None and tile.switchbox.g_switch.num_track > track:
                return tile.get_sb_circuit(side, track, io) == circuit
            else:
                return False
        elif isinstance(circuit, CB) or isinstance(circuit, EmptyCircuit):
            name = node.name
            if tile is not None and name in tile.ports:
                return tile.get_port_circuit(name) == circuit
            else:
                return False
        else:
            raise NotImplementedError()

    def get_sb_circuit(self, x: int, y: int, side: SwitchBoxSide, track: int,
                       io: SwitchBoxIO):
        tile = self.get_tile(x, y)
        if tile is not None:
            return tile.get_sb_circuit(side, track, io)
        return None

    def get_port_circuit(self, x: int, y: int, port_name: str):
        tile = self.get_tile(x, y)
        if tile is not None:
            return tile.get_port_circuit(port_name)

    def connect_switch(self, x0: int, y0: int, x1: int, y1: int,
                       expected_length: int, track: int,
                       policy: InterconnectPolicy):
        """connect switches with expected length in the region
        (x0, y0) <-> (x1, y1). it will tries to connect everything with
        expected length. connect in left -> right & top -> bottom fashion.

        policy:
            used when there is a tile with height larger than 1.
            PassThrough: allow to connect even if the wire length is different
                         from the expected_length. This will introduce
                         uncertainties of total wires and may introduce bugs.
                         one remedy for that is to break the tiles into smaller
                         tiles and assign switch box for each smaller tiles
            Ignore: ignore the connection if the wire length is different from
                    the expected_length. it is safe but may leave some tiles
                    unconnected
        """
        if x1 - expected_length <= x0 or y1 - expected_length <= y0:
            raise ValueError("the region has to be bigger than expected "
                             "length")

        if (x1 - x0) % expected_length != 0:
            raise ValueError("the region x has to be divisible by expected_"
                             "length")
        if (y1 - y0) % expected_length != 0:
            raise ValueError("the region y has to be divisible by expected_"
                             "length")

        # Note (keyi):
        # this code is very complex and hence has many comments. please do not
        # simplify this code unless you fully understand the logic flow.

        # left to right first
        for x in range(x0, x1 - expected_length, expected_length):
            for y in range(y0, y1, expected_length):
                if not self.__is_original_tile(x, y):
                    continue
                tile_from = self.get_tile(x, y)
                tile_to = self.get_tile(x + expected_length, y)
                # several outcomes to consider
                # 1. tile_to is empty -> apply policy
                # 2. tile_to is a reference -> apply policy
                if not self.__is_original_tile(x + expected_length, y):
                    if policy & InterconnectPolicy.Ignore:
                        continue
                    # find another tile longer than expected length that's
                    # within the range. because at this point we already know
                    # that the policy is passing through, just search the
                    # nearest tile (not tile reference) to meet the pass
                    # through requirement
                    x_ = x
                    while x_ < x1:
                        if self.__is_original_tile(x_, y):
                            tile_to = self.__grid[y][x_]
                            break
                        x_ += 1
                    # check again if we have resolved this issue
                    # since it's best effort, we will ignore if no tile left
                    # to connect
                    if not self.__is_original_tile(x + expected_length, y):
                        continue

                assert tile_to.y == tile_from.y
                # add to connection list
                # forward
                self.__add_sb_connection(tile_from, tile_to, track,
                                         SwitchBoxSide.EAST)

                # backward
                self.__add_sb_connection(tile_to, tile_from, track,
                                         SwitchBoxSide.WEST)

        # top to bottom this is very similar to the previous one (left to
        # right)
        for x in range(x0, x1):
            for y in range(y0, y1 - expected_length, expected_length):
                if not self.__is_original_tile(x, y):
                    continue
                tile_from = self.get_tile(x, y)
                tile_to = self.get_tile(x, y + expected_length)
                # several outcomes to consider
                # 1. tile_to is empty -> apply policy
                # 2. tile_to is a reference -> apply policy
                if not self.__is_original_tile(x, y + expected_length):
                    if policy & InterconnectPolicy.Ignore:
                        continue
                    y_ = y
                    while y_ < y1:
                        if self.__is_original_tile(x, y_):
                            tile_to = self.__grid[y_][x]
                            break
                        y_ += 1
                    # check again if we have resolved this issue
                    # since it's best effort, we will ignore if no tile left
                    # to connect
                    if not self.__is_original_tile(x, y + expected_length):
                        continue

                assert tile_to.x == tile_from.x
                # add to connection list
                # forward
                self.__add_sb_connection(tile_from, tile_to, track,
                                         SwitchBoxSide.SOUTH)
                # backward
                self.__add_sb_connection(tile_to, tile_from, track,
                                         SwitchBoxSide.NORTH)

    def __add_sb_connection(self, tile_from: TileCircuit,
                            tile_to: TileCircuit, track: int,
                            side: SwitchBoxSide):
        # connect the underlying routing graph
        sb_from = self.get_sb_circuit(tile_from.x, tile_from.y, side, track,
                                      SwitchBoxIO.SB_OUT)
        sb_to = self.get_sb_circuit(tile_to.x, tile_to.y,
                                    SwitchBoxSide.get_opposite_side(side),
                                    track, SwitchBoxIO.SB_IN)
        self.connect(sb_from, sb_to)

    def realize(self):
        # create muxs
        result = {}
        visited = set()
        width, height = self.get_size()
        for y in range(height):
            for x in range(width):
                tile = self.get_tile(x, y)
                if tile is not None and (tile.x, tile.y) not in visited:
                    result[(tile.x, tile.y)] = tile.realize()

                    visited.add((tile.x, tile.y))
        return result

    @staticmethod
    def compute_num_tracks(x_offset: int, y_offset: int,
                           x: int, y: int, track_info: Dict[int, int]):
        """compute the num of tracks needed for (x, y), given the track
        info"""
        x_diff = x - x_offset
        y_diff = y - y_offset
        result = 0
        for length, num_track in track_info.items():
            if x_diff % length == 0 and y_diff % length == 0:
                # it's the tile
                result += num_track
        return result

    def dump_routing_graph(self, filename: str):
        self.__graph.dump_graph(filename)

    def name(self):
        return f"Interconnect {self.track_width}"
