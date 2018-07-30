import shutil
import os
import glob
from bit_vector import BitVector

from simple_cb.simple_cb_magma import define_simple_cb
from simple_cb.simple_cb import gen_simple_cb
from simple_cb.simple_cb_genesis2 import simple_cb_wrapper

import magma as m
from common.testers import ResetTester, ConfigurationTester
from fault.test_vector_generator import generate_test_vectors_from_streams
from fault.random import random_bv

import pytest


def teardown_function():
    for item in glob.glob('genesis_*'):
        os.system(f"rm -r {item}")


# FIXME: this fails
# @pytest.mark.parametrize('num_tracks', range(2,10))
@pytest.mark.parametrize('num_tracks', [10])
def test_regression(num_tracks):
    params = {
        "width": 16,
        "num_tracks": num_tracks,
    }

    # Create magma circuit.
    magma_simple_cb = define_simple_cb(**params)
    m.compile(f"test_simple_cb/build/{magma_simple_cb.name}", magma_simple_cb,
              output="coreir-verilog")

    # Create genesis circuit.
    genesis_simple_cb = simple_cb_wrapper.generator()(
        **params, input_files=["simple_cb/genesis/simple_cb.vp"])
    genesis_verilog = "genesis_verif/simple_cb.v"
    shutil.copy(genesis_verilog, "test_simple_cb/build/")

    # TODO: Do we need this extra instantiation, could the function do it for
    # us?
    simple_cb_functional_model = gen_simple_cb(**params)()

    class MappedCB:
        def __init__(self, circuit):
            self.circuit = circuit
            self.renamed_ports = {
                "clk": "CLK",
                "reset": "ASYNCRESET",
                "out": "O"
            }

        def __getattr__(self, field):
            if self.circuit is magma_simple_cb:
                if field in self.renamed_ports:
                    field = self.renamed_ports[field]
                elif "in_" in field:
                    return self.circuit.I[int(field.split("_")[-1])]
            return getattr(self.circuit, field)

    class SimpleCBTester(ResetTester, ConfigurationTester):
        pass

    for simple_cb in [genesis_simple_cb, magma_simple_cb]:
        input_mapping = None if simple_cb is genesis_simple_cb else (
            lambda *args: (*args[-2:], *args[0].value, *args[1:-2]))

        simple_cb = MappedCB(simple_cb)
        tester = SimpleCBTester(simple_cb, simple_cb.clk,
                                simple_cb_functional_model, input_mapping)

        tester.zero_inputs()

        for config_data in [BitVector(x, 32) for x in range(0, 1)]:
            tester.reset()
            tester.configure(BitVector(0, 32), config_data)
            tester.test_vectors += \
                generate_test_vectors_from_streams(
                    simple_cb, simple_cb_functional_model, {
                        f"in_{i}": lambda name, port: random_bv(len(port))
                        for i in range(num_tracks)
                    })
        tester.compile_and_run(target="verilator",
                               directory="test_simple_cb/build",
                               flags=["-Wno-fatal"])
