from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from empire_stonks_ohlcv import (
    DailyBar,
    OHLCVParseError,
    ParsedListingBatch,
    ParsedProviderOutput,
    ProviderListing,
    STOOQ_HISTORY_SOURCE,
    StooqHistoryParser,
    StooqHistoryScope,
    inspect_stooq_history_archive,
)
from parser_contract import (
    InvalidParserCase,
    ValidParserCase,
    assert_parser_contract,
)


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "stooq"
    / "stooq_history"
    / "nasdaq_stocks_valid.txt"
)
HEADER = (
    b"<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,"
    b"<VOL>,<OPENINT>\n"
)


def _member(
    ticker: str,
    *rows: str,
    header: bytes = HEADER,
) -> bytes:
    body = "\n".join(rows).encode("utf-8")
    return header + body + (b"\n" if body else b"")


def _archive_bytes(
    *,
    nasdaq: dict[str, bytes] | None = None,
    nyse: dict[str, bytes] | None = None,
    nysemkt: dict[str, bytes] | None = None,
    extras: dict[str, bytes] | None = None,
) -> bytes:
    markets = {
        "nasdaq": nasdaq
        or {
            "1/aaa.us.txt": _member(
                "AAA.US",
                "AAA.US,D,20260102,000000,10,11,9,10.5,100.25,0",
            )
        },
        "nyse": nyse
        or {
            "2/bbb.us.txt": _member(
                "BBB.US",
                "BBB.US,D,20260102,000000,20,21,19,20.5,200,0",
            )
        },
        "nysemkt": nysemkt
        or {
            "ccc.us.txt": _member(
                "CCC.US",
                "CCC.US,D,20260102,000000,30,31,29,30.5,300,0",
            )
        },
    }
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for market, members in markets.items():
            for relative_path, payload in members.items():
                archive.writestr(
                    f"data/daily/us/{market} stocks/{relative_path}",
                    payload,
                )
        for member_path, payload in (extras or {}).items():
            archive.writestr(member_path, payload)
    return output.getvalue()


def _write_archive(tmp_path: Path, payload: bytes) -> Path:
    archive_path = tmp_path / "d_us_txt.zip"
    archive_path.write_bytes(payload)
    return archive_path


def _consume(parser: StooqHistoryParser) -> tuple:
    chunks = tuple(parser)
    return chunks, parser.summary


def test_parser_reports_progress_at_each_hundred_completed_members(
    tmp_path: Path,
) -> None:
    members = {
        f"1/t{index:03d}.us.txt": _member(
            f"T{index:03d}.US",
            (
                f"T{index:03d}.US,D,20260102,000000,10,11,9,10.5,"
                "100,0"
            ),
        )
        for index in range(100)
    }
    progress = []
    parser = StooqHistoryParser(
        _write_archive(tmp_path, _archive_bytes(nasdaq=members)),
        scope=StooqHistoryScope(
            effective_date=date(2026, 1, 6),
            markets=("nasdaq",),
        ),
        chunk_size=1000,
        progress_callback=progress.append,
    )

    _consume(parser)

    assert len(progress) == 1
    assert progress[0].files_discovered == 100
    assert progress[0].files_completed == 100
    assert progress[0].accepted_records == 100
    assert progress[0].chunks_emitted == 0
    assert parser.progress.files_completed == 100
    assert parser.progress.chunks_emitted == 1


def _flatten_batches(chunks: tuple) -> tuple[ParsedListingBatch, ...]:
    grouped: dict[ProviderListing, list[DailyBar]] = {}
    for chunk in chunks:
        for batch in chunk.batches:
            grouped.setdefault(batch.listing, []).extend(batch.bars)
    return tuple(
        ParsedListingBatch(listing=listing, bars=tuple(grouped[listing]))
        for listing in sorted(
            grouped,
            key=lambda item: (item.market, item.ticker),
        )
    )


def _parse_fixture_archive(tmp_path: Path, payload: bytes) -> ParsedProviderOutput:
    parser = StooqHistoryParser(
        _write_archive(tmp_path, payload),
        scope=StooqHistoryScope(effective_date=date(2026, 1, 6)),
        chunk_size=2,
    )
    chunks, _summary = _consume(parser)
    return ParsedProviderOutput(
        sources=(STOOQ_HISTORY_SOURCE,),
        batches=_flatten_batches(chunks),
    )


def _expected_output() -> ParsedProviderOutput:
    return ParsedProviderOutput(
        sources=(STOOQ_HISTORY_SOURCE,),
        batches=(
            ParsedListingBatch(
                listing=ProviderListing(
                    provider_code="STOOQ",
                    market="nasdaq",
                    ticker="AAA.US",
                ),
                bars=(
                    DailyBar(
                        trading_date=date(2026, 1, 2),
                        open=Decimal("10.1"),
                        high=Decimal("10.5"),
                        low=Decimal("9.9"),
                        close=Decimal("10.25"),
                        volume=Decimal("593562.95523744"),
                    ),
                    DailyBar(
                        trading_date=date(2026, 1, 5),
                        open=Decimal("10.25"),
                        high=Decimal("10.75"),
                        low=Decimal("10.2"),
                        close=Decimal("10.6"),
                        volume=Decimal("125094"),
                    ),
                ),
            ),
            ParsedListingBatch(
                listing=ProviderListing(
                    provider_code="STOOQ",
                    market="nyse",
                    ticker="BBB.US",
                ),
                bars=(
                    DailyBar(
                        trading_date=date(2026, 1, 2),
                        open=Decimal("20"),
                        high=Decimal("21"),
                        low=Decimal("19"),
                        close=Decimal("20.5"),
                        volume=Decimal("200"),
                    ),
                ),
            ),
            ParsedListingBatch(
                listing=ProviderListing(
                    provider_code="STOOQ",
                    market="nysemkt",
                    ticker="CCC.US",
                ),
                bars=(
                    DailyBar(
                        trading_date=date(2026, 1, 2),
                        open=Decimal("30"),
                        high=Decimal("31"),
                        low=Decimal("29"),
                        close=Decimal("30.5"),
                        volume=Decimal("300"),
                    ),
                ),
            ),
        ),
    )


def test_stooq_history_parser_passes_shared_contract(tmp_path: Path) -> None:
    fixture_payload = FIXTURE_PATH.read_bytes()
    valid_archive = _archive_bytes(
        nasdaq={"1/aaa.us.txt": fixture_payload},
    )
    invalid_header = _archive_bytes(
        nasdaq={
            "1/aaa.us.txt": _member(
                "AAA.US",
                "AAA.US,D,20260102,000000,10,11,9,10.5,100,0",
                header=b"ticker,period,date\n",
            )
        }
    )

    assert_parser_contract(
        parse=lambda payload: _parse_fixture_archive(tmp_path, payload),
        provider_code="STOOQ",
        volume_is_optional=False,
        valid_cases=(
            ValidParserCase(
                name="three markets and required fractional volume",
                payload=valid_archive,
                expected=_expected_output(),
            ),
        ),
        invalid_cases=(
            InvalidParserCase(
                name="invalid selected member header",
                payload=invalid_header,
            ),
        ),
    )


def test_discovery_is_recursive_filtered_and_deterministic(tmp_path: Path) -> None:
    archive_path = _write_archive(
        tmp_path,
        _archive_bytes(
            nasdaq={
                "3/zzz.us.txt": _member(
                    "ZZZ.US",
                    "ZZZ.US,D,20260102,000000,1,1,1,1,1,0",
                ),
                "1/aaa.us.txt": FIXTURE_PATH.read_bytes(),
            },
            extras={
                "data/daily/us/nasdaq etfs/ignored.us.txt": b"ignored",
            },
        ),
    )
    scope = StooqHistoryScope(
        effective_date=date(2026, 1, 6),
        markets=("nysemkt", "nasdaq"),
        tickers=("ZZZ.US", "CCC.US"),
    )

    discovery = inspect_stooq_history_archive(archive_path, scope=scope)

    assert scope.markets == ("nasdaq", "nysemkt")
    assert [
        (member.market, member.ticker, member.member_path)
        for member in discovery.members
    ] == [
        (
            "nasdaq",
            "ZZZ.US",
            "data/daily/us/nasdaq stocks/3/zzz.us.txt",
        ),
        (
            "nysemkt",
            "CCC.US",
            "data/daily/us/nysemkt stocks/ccc.us.txt",
        ),
    ]


def test_chunk_boundaries_are_stable_and_sizes_are_equivalent(
    tmp_path: Path,
) -> None:
    rows = tuple(
        f"AAA.US,D,2026010{day},000000,{day},{day + 1},{day - 1},"
        f"{day}.5,{day * 100},0"
        for day in range(1, 7)
    )
    archive_path = _write_archive(
        tmp_path,
        _archive_bytes(
            nasdaq={"1/aaa.us.txt": _member("AAA.US", *rows)},
        ),
    )
    scope = StooqHistoryScope(effective_date=date(2026, 1, 7))
    outputs = {}

    for chunk_size in (1, 2, 4, 20):
        parser = StooqHistoryParser(
            archive_path,
            scope=scope,
            chunk_size=chunk_size,
        )
        chunks, summary = _consume(parser)
        outputs[chunk_size] = _flatten_batches(chunks)
        assert [chunk.chunk_number for chunk in chunks] == list(
            range(1, len(chunks) + 1)
        )
        assert all(chunk.bar_count <= chunk_size for chunk in chunks)
        assert summary.accepted_records == 8
        assert summary.chunks_emitted == len(chunks)

    assert outputs[1] == outputs[2] == outputs[4] == outputs[20]

    repeated = StooqHistoryParser(
        archive_path,
        scope=scope,
        chunk_size=4,
    )
    first_chunks, _summary = _consume(repeated)
    second_chunks, _summary = _consume(
        StooqHistoryParser(
            archive_path,
            scope=scope,
            chunk_size=4,
        )
    )
    assert first_chunks == second_chunks


def test_date_filters_rejections_and_duplicates_are_counted(
    tmp_path: Path,
) -> None:
    archive_path = _write_archive(
        tmp_path,
        _archive_bytes(
            nasdaq={
                "1/aaa.us.txt": _member(
                    "AAA.US",
                    "AAA.US,D,20260101,000000,9,10,8,9.5,90,0",
                    "AAA.US,D,20260102,000000,10,11,9,10.5,100,0",
                    "AAA.US,D,20260102,000000,10,11,9,10.5,100,0",
                    "AAA.US,D,20260103,000000,10,11,9,10.5,100,0",
                    "AAA.US,D,20260103,000000,10,12,9,11.5,100,0",
                    "AAA.US,D,20260104,000000,10,9,8,10,100,0",
                    "AAA.US,D,20260107,000000,10,11,9,10.5,100,0",
                )
            },
        ),
    )
    parser = StooqHistoryParser(
        archive_path,
        scope=StooqHistoryScope(
            effective_date=date(2026, 1, 6),
            start_date=date(2026, 1, 2),
            markets=("nasdaq",),
            tickers=("AAA.US",),
        ),
        chunk_size=10,
    )

    chunks, summary = _consume(parser)

    assert [bar.trading_date for bar in _flatten_batches(chunks)[0].bars] == [
        date(2026, 1, 2)
    ]
    assert summary.input_rows == 7
    assert summary.date_filtered_rows == 1
    assert summary.accepted_records == 1
    assert summary.duplicate_rows_collapsed == 1
    assert summary.rejected_records == 3
    assert summary.rejected_rows == 4
    assert [issue.code for issue in summary.issue_samples] == [
        "stooq_invalid_ohlcv",
        "stooq_future_date",
        "stooq_conflicting_duplicate",
    ]


@pytest.mark.parametrize(
    ("scope", "error_type", "message"),
    (
        (
            {"effective_date": "2026-01-01"},
            TypeError,
            "effective_date",
        ),
        (
            {
                "effective_date": date(2026, 1, 1),
                "start_date": date(2026, 1, 2),
                "end_date": date(2026, 1, 1),
            },
            ValueError,
            "start_date",
        ),
        (
            {
                "effective_date": date(2026, 1, 1),
                "markets": ("NYSE",),
            },
            ValueError,
            "markets",
        ),
        (
            {
                "effective_date": date(2026, 1, 1),
                "tickers": ("aaa.us",),
            },
            ValueError,
            "tickers",
        ),
    ),
)
def test_scope_rejects_invalid_bounds_and_filters(
    scope: dict,
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        StooqHistoryScope(**scope)


def test_parser_is_one_shot_and_summary_requires_completion(
    tmp_path: Path,
) -> None:
    parser = StooqHistoryParser(
        _write_archive(tmp_path, _archive_bytes()),
        scope=StooqHistoryScope(effective_date=date(2026, 1, 6)),
        chunk_size=2,
    )

    with pytest.raises(RuntimeError, match="complete parser consumption"):
        _ = parser.summary
    iterator = iter(parser)
    next(iterator)
    with pytest.raises(RuntimeError, match="complete parser consumption"):
        _ = parser.summary
    tuple(iterator)
    assert parser.summary.files_completed == 3
    with pytest.raises(RuntimeError, match="one-shot"):
        iter(parser)


def test_archive_preflight_rejects_missing_market_and_wrong_name(
    tmp_path: Path,
) -> None:
    missing_market = io.BytesIO()
    with ZipFile(missing_market, "w") as archive:
        archive.writestr(
            "data/daily/us/nasdaq stocks/aaa.us.txt",
            _member(
                "AAA.US",
                "AAA.US,D,20260102,000000,10,11,9,10.5,100,0",
            ),
        )
    archive_path = _write_archive(tmp_path, missing_market.getvalue())
    scope = StooqHistoryScope(effective_date=date(2026, 1, 6))

    with pytest.raises(OHLCVParseError, match="missing a required"):
        inspect_stooq_history_archive(archive_path, scope=scope)

    wrong_name = tmp_path / "other.zip"
    wrong_name.write_bytes(_archive_bytes())
    with pytest.raises(OHLCVParseError, match="d_us_txt.zip"):
        inspect_stooq_history_archive(wrong_name, scope=scope)


@pytest.mark.parametrize(
    ("member_payload", "message"),
    (
        (
            HEADER,
            "does not contain any data rows",
        ),
        (
            _member(
                "WRONG.US",
                "WRONG.US,D,20260102,000000,10,11,9,10.5,100,0",
            ),
            "ticker does not match",
        ),
    ),
)
def test_selected_member_structure_failures_abort_deterministically(
    tmp_path: Path,
    member_payload: bytes,
    message: str,
) -> None:
    archive_path = _write_archive(
        tmp_path,
        _archive_bytes(nasdaq={"1/aaa.us.txt": member_payload}),
    )
    parser = StooqHistoryParser(
        archive_path,
        scope=StooqHistoryScope(effective_date=date(2026, 1, 6)),
        chunk_size=2,
    )

    for _attempt in range(2):
        candidate = StooqHistoryParser(
            archive_path,
            scope=parser.scope,
            chunk_size=2,
        )
        with pytest.raises(OHLCVParseError, match=message):
            tuple(candidate)


def test_parser_streams_members_without_zipfile_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = _write_archive(tmp_path, _archive_bytes())

    def fail_read(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("ZipFile.read must not load a complete member")

    monkeypatch.setattr(ZipFile, "read", fail_read)
    parser = StooqHistoryParser(
        archive_path,
        scope=StooqHistoryScope(effective_date=date(2026, 1, 6)),
        chunk_size=2,
    )

    chunks, summary = _consume(parser)

    assert sum(chunk.bar_count for chunk in chunks) == 3
    assert summary.accepted_records == 3
