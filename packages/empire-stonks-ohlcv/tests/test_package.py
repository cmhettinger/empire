import empire_core
import empire_stonks_ohlcv


def test_package_and_core_dependency_import() -> None:
    assert empire_stonks_ohlcv.__doc__
    assert empire_core.__doc__
