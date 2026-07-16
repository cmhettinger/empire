from empire_stonks_ohlcv import (
    EmpireStonksOHLCVError,
    OHLCVAcquisitionError,
    OHLCVConfigError,
    OHLCVParseError,
    OHLCVPersistenceError,
)


def test_public_exception_hierarchy() -> None:
    exception_types = (
        OHLCVAcquisitionError,
        OHLCVConfigError,
        OHLCVParseError,
        OHLCVPersistenceError,
    )

    assert all(
        issubclass(error_type, EmpireStonksOHLCVError)
        for error_type in exception_types
    )


def test_public_exports_are_explicit() -> None:
    import empire_stonks_ohlcv

    assert empire_stonks_ohlcv.__all__ == [
        "EODDataCredentials",
        "EmpireStonksOHLCVError",
        "OHLCVAcquisitionError",
        "OHLCVConfig",
        "OHLCVConfigError",
        "OHLCVParseError",
        "OHLCVPersistenceError",
        "ProviderListing",
    ]
