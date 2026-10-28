"""Every layer imports cleanly (also gives coverage something to measure from day one)."""

import importlib

import pytest

import slim_prep


@pytest.mark.parametrize("layer", ["domain", "persistence", "service"])
def test_layer_imports(layer):
    module = importlib.import_module(f"slim_prep.{layer}")
    assert module.__doc__


def test_version():
    assert slim_prep.__version__ == "0.1.0"
