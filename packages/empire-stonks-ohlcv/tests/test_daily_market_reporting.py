from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from empire_stonks_ohlcv.daily_market_reporting import (
    DailyEquityRow,
    DailyMarketBasketSnapshot,
    DailyMarketUniverse,
    EODDataDailyMarketReport,
    HighVolumeLowMovementRow,
    MarketBreadth,
    MoveBucket,
    PriceAnomaly,
    VolumeAnomaly,
    build_eoddata_daily_market_report,
)
from empire_stonks_ohlcv.daily_market_baskets import DAILY_MARKET_BASKETS
from empire_stonks_ohlcv.reports.eoddata_daily_market_pdf import (
    EODDATA_DAILY_MARKET_PDF_REPORT_ID,
    render_eoddata_daily_market_pdf,
)


TRADING_DATE = date(2026, 7, 17)
GENERATED_AT = datetime(2026, 7, 18, 1, 30, tzinfo=UTC)


def test_configured_baskets_have_stable_unique_members() -> None:
    assert tuple(len(spec.tickers) for spec in DAILY_MARKET_BASKETS) == (7, 30, 100)
    assert tuple(spec.code for spec in DAILY_MARKET_BASKETS) == (
        "MAG7",
        "DOW30",
        "NASDAQ100",
    )
    assert all(
        len(spec.tickers) == len(set(spec.tickers))
        and all(ticker == ticker.upper() for ticker in spec.tickers)
        for spec in DAILY_MARKET_BASKETS
    )


class FakeCursor:
    def __init__(self) -> None:
        self.rows: list[tuple[object, ...]] = []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        marker = query.split("empire_daily_market:", 1)[1].split(" ", 1)[0]
        self.calls.append((marker, params))
        if marker == "basket":
            configured = tuple(str(value) for value in params[0])
            self.rows = [
                (
                    "NASDAQ",
                    ticker,
                    f"{ticker} Incorporated",
                    "USD",
                    Decimal("100"),
                    Decimal("1"),
                    Decimal("0.01"),
                    Decimal("1000000"),
                )
                for ticker in configured[:2]
            ]
            return
        if marker == "high_volume_low_movement":
            self.rows = [
                (
                    "NYSE",
                    "FLAT",
                    "Flat Company",
                    "USD",
                    Decimal("99.5"),
                    Decimal("101"),
                    Decimal("99"),
                    Decimal("100"),
                    Decimal("0.25"),
                    Decimal("0.0025"),
                    Decimal("50000000"),
                )
            ]
            return
        self.rows = {
            "universe": [(12, 9, 2, 1)],
            "breadth": [
                ("NYSE", 4, 4, 3, 1, 0, 0, 1000, Decimal("0.0125")),
                ("NASDAQ", 3, 2, 1, 1, 0, 1, 2000, Decimal("-0.005")),
                ("AMEX", 2, 2, 0, 1, 1, 0, 300, Decimal("-0.02")),
            ],
            "move_buckets": [
                ("Down 2-5%", 0, 1, 1),
                ("Unchanged", 0, 0, 1),
                ("Up 2-5%", 2, 1, 0),
            ],
            "movers_desc": [
                ("NYSE", "AAA", "Alpha", "USD", 12, 2, Decimal("0.20"), 500),
                ("NASDAQ", "BBB", "Beta", "USD", 21, 1, Decimal("0.05"), 800),
            ],
            "movers_asc": [
                ("NYSE", "CCC", "Gamma", "USD", 8, -2, Decimal("-0.20"), 400),
            ],
            "volume_leaders": [
                ("NASDAQ", "BBB", "Beta", "USD", 21, 1, Decimal("0.05"), 800),
            ],
            "price_anomalies": [
                (
                    "AMEX",
                    "DDD",
                    "Delta",
                    "EXTREME UP MOVE",
                    4,
                    Decimal("0.35"),
                    Decimal("0.10"),
                    900,
                )
            ],
            "volume_anomalies": [
                (
                    "NYSE",
                    "AAA",
                    "Alpha",
                    5000,
                    500,
                    Decimal("10"),
                    Decimal("0.20"),
                )
            ],
        }[marker]

    def fetchone(self) -> tuple[object, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


def test_builds_date_scoped_provider_native_market_report() -> None:
    cursor = FakeCursor()

    report = build_eoddata_daily_market_report(
        cursor=cursor,
        trading_date=TRADING_DATE,
        generated_at=GENERATED_AT,
    )

    assert report.universe == DailyMarketUniverse(12, 9, 2, 1)
    assert tuple(item.market for item in report.breadth) == (
        "NYSE",
        "NASDAQ",
        "AMEX",
    )
    assert report.comparable_count == 8
    assert report.advancers == 4
    assert report.decliners == 3
    assert report.unchanged == 1
    assert report.missing_comparison == 1
    assert report.total_volume == Decimal("3300")
    assert report.winners[0].ticker == "AAA"
    assert report.losers[0].changepct == Decimal("-0.20")
    assert report.price_anomalies[0].anomaly_type == "EXTREME UP MOVE"
    assert report.volume_anomalies[0].volume_multiple == Decimal("10")
    assert tuple(basket.code for basket in report.baskets) == (
        "MAG7",
        "DOW30",
        "NASDAQ100",
    )
    assert report.basket("mag7") is not None
    assert report.basket("MAG7").available_count == 2  # type: ignore[union-attr]
    assert report.basket("unknown") is None
    assert report.high_volume_low_movement[0].ticker == "FLAT"
    assert report.high_volume_low_movement[0].changepct == Decimal("0.0025")
    assert [item[0] for item in cursor.calls] == [
        "universe",
        "breadth",
        "move_buckets",
        "movers_desc",
        "movers_asc",
        "volume_leaders",
        "price_anomalies",
        "volume_anomalies",
        "basket",
        "basket",
        "basket",
        "high_volume_low_movement",
    ]
    assert all(call[1][0] == "EODDATA" for call in cursor.calls[:8])
    assert all(call[1][1] == "EODDATA" for call in cursor.calls[8:11])
    assert cursor.calls[11][1][0] == "EODDATA"
    assert cursor.calls[11][1][2] == Decimal("0.005")
    assert cursor.calls[11][1][3] == 12
    assert cursor.calls[3][1][2] == 12
    assert cursor.calls[4][1][2] == 12
    assert cursor.calls[5][1][2] == 12
    assert all(TRADING_DATE in call[1] for call in cursor.calls)


def test_missing_market_breadth_is_filled_with_zeroes() -> None:
    cursor = FakeCursor()
    original_execute = cursor.execute

    def execute(query: str, params: tuple[object, ...]) -> None:
        original_execute(query, params)
        if "empire_daily_market:breadth" in query:
            cursor.rows = cursor.rows[:1]

    cursor.execute = execute  # type: ignore[method-assign]

    report = build_eoddata_daily_market_report(
        cursor=cursor,
        trading_date=TRADING_DATE,
        generated_at=GENERATED_AT,
    )

    assert report.breadth[0].equity_count == 4
    assert report.breadth[1].equity_count == 0
    assert report.breadth[2].equity_count == 0


def test_renders_branded_daily_market_pdf(tmp_path: Path) -> None:
    report = _complete_report()

    result = render_eoddata_daily_market_pdf(
        report=report,
        output_dir=tmp_path,
    )

    path = result.primary_artifact.path
    assert result.report.report_id == EODDATA_DAILY_MARKET_PDF_REPORT_ID
    assert path.name == "daily-market-report.pdf"
    assert path.read_bytes().startswith(b"%PDF-")
    assert path.stat().st_size > 20_000


def _complete_report() -> EODDataDailyMarketReport:
    equities = (
        DailyEquityRow(
            market="NYSE",
            ticker="AAA",
            name="Alpha Holdings Incorporated",
            currency="USD",
            close=Decimal("12.34"),
            change=Decimal("1.23"),
            changepct=Decimal("0.1107"),
            volume=Decimal("12345678"),
        ),
        DailyEquityRow(
            market="NASDAQ",
            ticker="BBB",
            name="Beta Technologies Corporation",
            currency="USD",
            close=Decimal("98.76"),
            change=Decimal("-4.56"),
            changepct=Decimal("-0.0441"),
            volume=Decimal("9876543"),
        ),
        DailyEquityRow(
            market="AMEX",
            ticker="CCC",
            name="Gamma Resources Limited",
            currency="USD",
            close=Decimal("4.25"),
            change=Decimal("0.25"),
            changepct=Decimal("0.0625"),
            volume=Decimal("543210"),
        ),
    )
    return EODDataDailyMarketReport(
        trading_date=TRADING_DATE,
        generated_at=GENERATED_AT,
        universe=DailyMarketUniverse(3500, 3100, 300, 100),
        breadth=(
            MarketBreadth("NYSE", 1200, 1190, 700, 480, 10, 10, Decimal("1.2e9"), Decimal("0.004")),
            MarketBreadth(
                "NASDAQ",
                1500,
                1480,
                600,
                860,
                20,
                20,
                Decimal("2.4e9"),
                Decimal("-0.006"),
            ),
            MarketBreadth("AMEX", 400, 390, 180, 200, 10, 10, Decimal("2.3e8"), Decimal("-0.001")),
        ),
        move_buckets=(
            MoveBucket("Down 10%+", 8, 12, 3),
            MoveBucket("Down 5-10%", 25, 31, 8),
            MoveBucket("Down 2-5%", 110, 150, 35),
            MoveBucket("Down 0-2%", 337, 667, 154),
            MoveBucket("Unchanged", 10, 20, 10),
            MoveBucket("Up 0-2%", 510, 440, 125),
            MoveBucket("Up 2-5%", 150, 120, 45),
            MoveBucket("Up 5-10%", 50, 35, 8),
            MoveBucket("Up 10%+", 10, 5, 2),
        ),
        winners=(equities[0], equities[2]),
        losers=(equities[1],),
        volume_leaders=equities,
        price_anomalies=(
            PriceAnomaly(
                "NYSE",
                "AAA",
                "Alpha Holdings Incorporated",
                "EXTREME UP MOVE",
                Decimal("12.34"),
                Decimal("0.35"),
                Decimal("0.18"),
                Decimal("12345678"),
            ),
        ),
        volume_anomalies=(
            VolumeAnomaly(
                "NASDAQ",
                "BBB",
                "Beta Technologies Corporation",
                Decimal("9876543"),
                Decimal("850000"),
                Decimal("11.62"),
                Decimal("-0.0441"),
            ),
        ),
        baskets=(
            DailyMarketBasketSnapshot(
                code="MAG7",
                title="Magnificent Seven",
                membership_version="empire-v1",
                configured_count=7,
                rows=equities,
                missing_tickers=("AAPL", "MSFT", "AMZN", "NVDA"),
            ),
            DailyMarketBasketSnapshot(
                code="DOW30",
                title="Dow 30 Configured Basket",
                membership_version="empire-v1",
                configured_count=30,
                rows=equities,
                missing_tickers=(),
            ),
            DailyMarketBasketSnapshot(
                code="NASDAQ100",
                title="Nasdaq-100 Configured Basket",
                membership_version="empire-v1",
                configured_count=100,
                rows=equities,
                missing_tickers=(),
            ),
        ),
        high_volume_low_movement=(
            HighVolumeLowMovementRow(
                market="NYSE",
                ticker="FLAT",
                name="Flat Company Incorporated",
                currency="USD",
                open=Decimal("99.50"),
                high=Decimal("101.00"),
                low=Decimal("99.00"),
                close=Decimal("100.00"),
                change=Decimal("0.25"),
                changepct=Decimal("0.0025"),
                volume=Decimal("50000000"),
            ),
        ),
    )
