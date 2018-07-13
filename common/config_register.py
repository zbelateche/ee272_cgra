import magma as m
import mantle


def DefineConfigRegister(width, address, has_reset, _type=m.Bits):
    """
    Generate a config register with address @address. This module has an input
    port named @addr, which is compared against the generator parameter
    (constant) @address. If the two are equal, then the clock enable on the
    underlying register is high.
    """
    if _type not in {m.Bits, m.UInt, m.SInt}:
        raise ValueError("Argument _type must be Bits, UInt, or SInt")
    T = _type(width)

    AddressType = type(address)
    if not isinstance(AddressType, (m.BitsKind, m.UIntKind, m.SIntKind)):
        raise ValueError("Argument address must be instance of "
                         "Bits, UInt, or SInt")

    def get_name():
        type_name = str(T).replace("(", "$").replace(")", "$")
        return "ConfigRegister_%s_%s_%s" % (type_name, address, has_reset)

    class _ConfigRegister(m.Circuit):
        name = get_name()
        IO = ["I", m.In(T), "O", m.Out(T), "addr", m.In(AddressType)]
        IO += m.ClockInterface(has_ce=True, has_reset=has_reset)

        @classmethod
        def definition(io):
            reg = mantle.Register(n=width,
                                  init=0,
                                  has_ce=True,
                                  has_reset=has_reset)
            m.wire(io.I, reg.I)
            addr_cmp = mantle.EQ(AddressType.N)
            m.wire(addr_cmp.I0, io.addr)
            m.wire(addr_cmp.I1, address)
            m.wire(addr_cmp.O, reg.CE)
            if has_reset:
                m.wire(reg.RESET, io.RESET)
            m.wire(reg.O, io.O)

    return _ConfigRegister