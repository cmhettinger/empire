from importlib.metadata import version

import numpy
import talib

import empire_stonks_tech_indicators


def test_package_and_pinned_runtime_import() -> None:
    assert empire_stonks_tech_indicators.__doc__
    assert version("empire-stonks-tech-indicators") == "0.1.0"
    assert numpy.__version__ == "2.4.6"
    assert version("TA-Lib") == "0.7.1"
    assert talib.__ta_version__.decode("ascii").startswith("0.7.1 ")
