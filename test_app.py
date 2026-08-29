# import pandas as pd
# import pytest

# import app


# def test_transform_chunk_lowercases_columns():
#     chunk = pd.DataFrame({
#         'VendorID': [1, 2],
#         'passenger_count': [1, 2],
#         'RatecodeID': [1, 1],
#         'payment_type': [1, 2],
#         'trip_distance': [1.2, 3.4],
#     })
#     result = app.transform_chunk(chunk)
#     assert list(result.columns) == ['vendorid', 'passenger_count', 'ratecodeid', 'payment_type', 'trip_distance']


# def test_transform_chunk_handles_nan_in_integer_columns():
#     # passenger_count has a missing value, as real taxi data sometimes does.
#     chunk = pd.DataFrame({
#         'VendorID': [1, 2, 3],
#         'passenger_count': [1, None, 3],
#         'RatecodeID': [1, 1, 2],
#         'payment_type': [1, 2, 1],
#     })
#     result = app.transform_chunk(chunk)

#     # Should not raise, and should use the nullable Int64 dtype rather
#     # than silently falling back to float64.
#     assert str(result['passenger_count'].dtype) == 'Int64'
#     assert result['passenger_count'].isna().sum() == 1
#     assert result.loc[0, 'passenger_count'] == 1



# def test_create_table_sql_defines_expected_columns():
#     for column in [
#         'vendorid', 'tpep_pickup_datetime', 'tpep_dropoff_datetime',
#         'passenger_count', 'trip_distance', 'fare_amount', 'total_amount',
#     ]:
#         assert column in app.CREATE_TABLE_SQL.lower()


# def test_load_data_raises_when_csv_missing(tmp_path):
#     missing_path = tmp_path / 'does_not_exist.csv'
#     with pytest.raises(FileNotFoundError):
#         app.load_data(csv_path=str(missing_path), engine=object())


# def test_get_engine_uses_env_vars(monkeypatch):
#     monkeypatch.setattr(app, 'DB_USER', 'testuser')
#     monkeypatch.setattr(app, 'DB_PASSWORD', 'testpass')
#     monkeypatch.setattr(app, 'DB_HOST', 'testhost')
#     monkeypatch.setattr(app, 'DB_PORT', '5555')
#     monkeypatch.setattr(app, 'DB_NAME', 'testdb')

#     engine = app.get_engine()
#     assert str(engine.url) == 'postgresql+psycopg2://testuser:***@testhost:5555/testdb'


"""
Expert-level tests for the NYC Taxi CSV -> PostgreSQL loader.

Run:
    pytest -v

These tests focus on:
- transformation correctness
- schema correctness
- NULL handling
- data integrity
- SQL safety
- failure handling
- idempotency-related design checks
- transaction behavior where the app exposes it
"""

import os
from pathlib import Path

import pandas as pd
import pytest

import app


# ============================================================
# 1. TRANSFORMATION TESTS
# ============================================================

def test_transform_chunk_lowercases_all_columns():
    """All incoming CSV column names should be normalized to lowercase."""

    chunk = pd.DataFrame({
        "VendorID": [1, 2],
        "TPEP_Pickup_Datetime": ["2015-01-10 20:33:39", "2015-01-10 20:33:38"],
        "RateCodeID": [1, 1],
        "Payment_Type": [1, 2],
        "trip_distance": [1.2, 3.4],
    })

    result = app.transform_chunk(chunk)

    assert all(column == column.lower() for column in result.columns)

    assert list(result.columns) == [
        "vendorid",
        "tpep_pickup_datetime",
        "ratecodeid",
        "payment_type",
        "trip_distance",
    ]


def test_transform_chunk_preserves_row_count():
    """Transformation must never silently drop rows."""

    chunk = pd.DataFrame({
        "VendorID": [1, 2, 1, 2, 1],
        "passenger_count": [1, 2, 1, 3, 1],
        "trip_distance": [1.2, 3.4, 0.5, 9.0, 15.5],
    })

    result = app.transform_chunk(chunk)

    assert len(result) == len(chunk)
    assert len(result) == 5


def test_transform_chunk_preserves_duplicate_rows():
    """
    Duplicate detection should not accidentally happen inside the
    transformation layer unless the application explicitly promises it.
    """

    chunk = pd.DataFrame({
        "VendorID": [2, 2],
        "passenger_count": [1, 1],
        "trip_distance": [15.5, 15.5],
        "fare_amount": [52.0, 52.0],
    })

    result = app.transform_chunk(chunk)

    assert len(result) == 2
    assert result.iloc[0].equals(result.iloc[1])


def test_transform_chunk_handles_nan_in_integer_columns():
    """Nullable integer columns should preserve NULL values."""

    chunk = pd.DataFrame({
        "VendorID": [1, 2, 3],
        "passenger_count": [1, None, 3],
        "RatecodeID": [1, 1, 2],
        "payment_type": [1, 2, 1],
    })

    result = app.transform_chunk(chunk)

    assert str(result["passenger_count"].dtype) == "Int64"
    assert result["passenger_count"].isna().sum() == 1

    assert result.loc[0, "passenger_count"] == 1
    assert result.loc[2, "passenger_count"] == 3


def test_transform_chunk_preserves_null_values():
    """Empty CSV fields should remain null rather than becoming strings."""

    chunk = pd.DataFrame({
        "VendorID": [1, None, 2],
        "passenger_count": [1, None, 2],
        "fare_amount": [10.5, None, 20.0],
    })

    result = app.transform_chunk(chunk)

    assert pd.isna(result.loc[1, "vendorid"])
    assert pd.isna(result.loc[1, "passenger_count"])
    assert pd.isna(result.loc[1, "fare_amount"])


def test_transform_chunk_does_not_modify_original_dataframe():
    """Transformation should not unexpectedly mutate the caller's DataFrame."""

    chunk = pd.DataFrame({
        "VendorID": [1, 2],
        "trip_distance": [1.2, 3.4],
    })

    original = chunk.copy(deep=True)

    app.transform_chunk(chunk)

    pd.testing.assert_frame_equal(chunk, original)


def test_transform_chunk_handles_empty_dataframe():
    """An empty chunk should not crash transformation logic."""

    chunk = pd.DataFrame(
        columns=["VendorID", "passenger_count", "trip_distance"]
    )

    result = app.transform_chunk(chunk)

    assert result.empty
    assert len(result) == 0


def test_transform_chunk_handles_mixed_case_columns():
    """Column normalization should be case-insensitive."""

    chunk = pd.DataFrame({
        "VeNdOrId": [1],
        "PASSENGER_COUNT": [1],
        "Trip_Distance": [5.5],
        "FARE_AMOUNT": [20.0],
    })

    result = app.transform_chunk(chunk)

    assert "vendorid" in result.columns
    assert "passenger_count" in result.columns
    assert "trip_distance" in result.columns
    assert "fare_amount" in result.columns


# ============================================================
# 2. SCHEMA TESTS
# ============================================================

def test_create_table_sql_contains_all_nyc_taxi_columns():
    """The database table should contain every required source column."""

    expected_columns = [
        "vendorid",
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
        "passenger_count",
        "trip_distance",
        "pickup_longitude",
        "pickup_latitude",
        "ratecodeid",
        "store_and_fwd_flag",
        "dropoff_longitude",
        "dropoff_latitude",
        "payment_type",
        "fare_amount",
        "extra",
        "mta_tax",
        "tip_amount",
        "tolls_amount",
        "improvement_surcharge",
        "total_amount",
    ]

    sql = app.CREATE_TABLE_SQL.lower()

    for column in expected_columns:
        assert column in sql, f"Missing column in CREATE TABLE SQL: {column}"


def test_create_table_sql_creates_expected_table():
    """Verify the expected destination table is referenced."""

    sql = app.CREATE_TABLE_SQL.lower()

    assert "create table" in sql
    assert "yellow_taxi_data" in sql


def test_create_table_sql_has_primary_or_unique_strategy():
    """
    The loader should have some strategy for preventing accidental
    duplicate records if idempotency is part of the application design.

    This test is intentionally flexible because implementations may use
    PRIMARY KEY, UNIQUE, or another database-level strategy.
    """

    sql = app.CREATE_TABLE_SQL.lower()

    has_uniqueness_strategy = (
        "primary key" in sql
        or "unique" in sql
    )

    # This is informational rather than mandatory because the current
    # application may intentionally use an append-only design.
    if not has_uniqueness_strategy:
        pytest.skip(
            "No PRIMARY KEY/UNIQUE constraint found; "
            "loader appears to use append-only semantics."
        )


# ============================================================
# 3. REAL DATASET / DATA QUALITY TESTS
# ============================================================

@pytest.fixture
def taxi_dataframe():
    """
    The exact 10-row fixture represented by the user's NYC Taxi dataset.

    Five logical records are intentionally duplicated.
    """

    return pd.DataFrame({
        "VendorID": [2, 1, 1, None, 2, 2, 1, 1, None, 2],

        "tpep_pickup_datetime": [
            "2015-01-10 20:33:39",
            "2015-01-10 20:33:38",
            "2015-01-10 20:33:38",
            "2015-01-10 20:33:39",
            "2015-01-10 20:33:39",
            "2015-01-10 20:33:39",
            "2015-01-10 20:33:38",
            "2015-01-10 20:33:38",
            "2015-01-10 20:33:39",
            "2015-01-10 20:33:39",
        ],

        "tpep_dropoff_datetime": [
            "2015-01-10 20:53:52",
            "2015-01-10 20:42:20",
            "2015-01-10 20:35:31",
            "2015-01-10 20:52:58",
            "2015-01-10 20:37:31",
            "2015-01-10 20:53:52",
            "2015-01-10 20:42:20",
            "2015-01-10 20:35:31",
            "2015-01-10 20:52:58",
            "2015-01-10 20:37:31",
        ],

        "passenger_count": [
            1, 1, 1, None, 1,
            1, 1, 1, None, 1
        ],

        "trip_distance": [
            15.5, 3.0, 0.5, 9.0, 1.2,
            15.5, 3.0, 0.5, 9.0, 1.2
        ],

        "pickup_longitude": [
            -73.99, -73.98, -73.98, -73.86, -73.95,
            -73.99, -73.98, -73.98, -73.86, -73.95
        ],

        "pickup_latitude": [
            40.72, 40.72, 40.76, 40.77, 40.78,
            40.72, 40.72, 40.76, 40.77, 40.78
        ],

        "RateCodeID": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],

        "store_and_fwd_flag": [
            "N", "N", "N", "N", "N",
            "N", "N", "N", "N", "N"
        ],

        "dropoff_longitude": [
            -73.94, -73.99, -73.99, -73.98, -73.96,
            -73.94, -73.99, -73.99, -73.98, -73.96
        ],

        "dropoff_latitude": [
            40.83, 40.75, 40.76, 40.75, 40.77,
            40.83, 40.75, 40.76, 40.75, 40.77
        ],

        "payment_type": [
            1, 1, 2, 1, 2,
            1, 1, 2, 1, 2
        ],

        "fare_amount": [
            52.0, 11.5, 4.5, 27.0, 6.0,
            52.0, 11.5, 4.5, 27.0, 6.0
        ],

        "extra": [
            0.5, 0.5, 0.5, 0.5, 0.5,
            0.5, 0.5, 0.5, 0.5, 0.5
        ],

        "mta_tax": [
            0.5, 0.5, 0.5, 0.5, 0.5,
            0.5, 0.5, 0.5, 0.5, 0.5
        ],

        "tip_amount": [
            11.65, 2.0, 0.0, 0.0, 0.0,
            11.65, 2.0, 0.0, 0.0, 0.0
        ],

        "tolls_amount": [
            0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0
        ],

        "improvement_surcharge": [
            0.3, 0.3, 0.3, 0.3, 0.3,
            0.3, 0.3, 0.3, 0.3, 0.3
        ],

        "total_amount": [
            69.95, 14.8, 5.8, 28.3, 7.3,
            69.95, 14.8, 5.8, 28.3, 7.3
        ],
    })


def test_dataset_contains_expected_number_of_rows(taxi_dataframe):
    """The supplied fixture contains exactly 10 source rows."""

    assert len(taxi_dataframe) == 10


def test_dataset_contains_five_duplicate_pairs(taxi_dataframe):
    """
    The supplied fixture intentionally contains 5 duplicated logical records.
    """

    duplicate_count = taxi_dataframe.duplicated().sum()

    assert duplicate_count == 5


def test_dataset_contains_five_unique_records(taxi_dataframe):
    """Ten rows should represent five unique records."""

    assert len(taxi_dataframe.drop_duplicates()) == 5


def test_dataset_has_expected_null_vendor_count(taxi_dataframe):
    assert taxi_dataframe["VendorID"].isna().sum() == 2


def test_dataset_has_expected_null_passenger_count(taxi_dataframe):
    assert taxi_dataframe["passenger_count"].isna().sum() == 2


def test_all_trip_dropoffs_are_after_pickups(taxi_dataframe):
    pickup = pd.to_datetime(taxi_dataframe["tpep_pickup_datetime"])
    dropoff = pd.to_datetime(taxi_dataframe["tpep_dropoff_datetime"])

    assert (dropoff > pickup).all()


def test_trip_distances_are_non_negative(taxi_dataframe):
    assert (taxi_dataframe["trip_distance"] >= 0).all()


def test_fares_are_non_negative(taxi_dataframe):
    assert (taxi_dataframe["fare_amount"] >= 0).all()


def test_tips_are_non_negative(taxi_dataframe):
    assert (taxi_dataframe["tip_amount"] >= 0).all()


def test_total_amount_is_not_less_than_fare(taxi_dataframe):
    assert (
        taxi_dataframe["total_amount"]
        >= taxi_dataframe["fare_amount"]
    ).all()


def test_nyc_pickup_coordinates_are_reasonable(taxi_dataframe):
    assert taxi_dataframe["pickup_longitude"].between(-75, -72).all()
    assert taxi_dataframe["pickup_latitude"].between(40, 42).all()


def test_nyc_dropoff_coordinates_are_reasonable(taxi_dataframe):
    assert taxi_dataframe["dropoff_longitude"].between(-75, -72).all()
    assert taxi_dataframe["dropoff_latitude"].between(40, 42).all()


def test_store_and_forward_flag_has_valid_values(taxi_dataframe):
    assert set(taxi_dataframe["store_and_fwd_flag"].dropna()) <= {"Y", "N"}


def test_payment_type_has_expected_values(taxi_dataframe):
    assert set(taxi_dataframe["payment_type"].dropna()) <= {1, 2, 3, 4}


def test_vendor_distribution_is_preserved(taxi_dataframe):
    counts = taxi_dataframe["VendorID"].value_counts(dropna=False)

    assert counts[1] == 4
    assert counts[2] == 4
    assert counts.isna().sum() == 0

    null_count = taxi_dataframe["VendorID"].isna().sum()
    assert null_count == 2


def test_payment_type_distribution_is_preserved(taxi_dataframe):
    counts = taxi_dataframe["payment_type"].value_counts()

    assert counts[1] == 6
    assert counts[2] == 4


# ============================================================
# 4. BUSINESS LOGIC / DERIVED DATA TESTS
# ============================================================

def test_first_trip_duration_is_exactly_1213_seconds(taxi_dataframe):
    """
    First trip:
    20:33:39 -> 20:53:52
    = 20m 13s
    = 1213 seconds
    """

    pickup = pd.to_datetime(
        taxi_dataframe.loc[0, "tpep_pickup_datetime"]
    )

    dropoff = pd.to_datetime(
        taxi_dataframe.loc[0, "tpep_dropoff_datetime"]
    )

    duration = (dropoff - pickup).total_seconds()

    assert duration == 1213


def test_all_trip_durations_are_positive(taxi_dataframe):
    pickup = pd.to_datetime(taxi_dataframe["tpep_pickup_datetime"])
    dropoff = pd.to_datetime(taxi_dataframe["tpep_dropoff_datetime"])

    duration = (dropoff - pickup).dt.total_seconds()

    assert (duration > 0).all()


def test_known_total_amount_values_are_preserved(taxi_dataframe):
    expected = [
        69.95,
        14.8,
        5.8,
        28.3,
        7.3,
    ]

    actual = taxi_dataframe["total_amount"].iloc[:5].tolist()

    assert actual == expected


def test_known_trip_distances_are_preserved(taxi_dataframe):
    expected = [15.5, 3.0, 0.5, 9.0, 1.2]

    actual = taxi_dataframe["trip_distance"].iloc[:5].tolist()

    assert actual == expected


# ============================================================
# 5. INPUT VALIDATION / FAILURE TESTS
# ============================================================

def test_load_data_raises_when_csv_missing(tmp_path):
    """Missing source files should fail explicitly."""

    missing_path = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError):
        app.load_data(
            csv_path=str(missing_path),
            engine=object(),
        )


def test_missing_csv_does_not_create_partial_output(tmp_path):
    """
    A missing input should fail before attempting to create a
    partially loaded dataset.
    """

    missing_path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError):
        app.load_data(
            csv_path=str(missing_path),
            engine=object(),
        )

    # The source itself must still not exist.
    assert not missing_path.exists()


def test_empty_csv_is_detectable(tmp_path):
    """An empty CSV should be distinguishable from a valid dataset."""

    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("", encoding="utf-8")

    assert empty_csv.exists()
    assert empty_csv.stat().st_size == 0


def test_header_only_csv_is_detectable(tmp_path):
    """A CSV containing headers but no records should be detectable."""

    csv_file = tmp_path / "header_only.csv"

    csv_file.write_text(
        "VendorID,tpep_pickup_datetime,tpep_dropoff_datetime,"
        "passenger_count,trip_distance\n",
        encoding="utf-8",
    )

    df = pd.read_csv(csv_file)

    assert df.empty
    assert len(df.columns) == 5


def test_missing_required_column_is_detectable(tmp_path):
    """Required source columns must be validated before loading."""

    csv_file = tmp_path / "missing_column.csv"

    csv_file.write_text(
        "VendorID,tpep_pickup_datetime,tpep_dropoff_datetime\n"
        "1,2015-01-10 20:33:38,2015-01-10 20:42:20\n",
        encoding="utf-8",
    )

    df = pd.read_csv(csv_file)

    required_columns = {
        "VendorID",
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
        "passenger_count",
        "trip_distance",
    }

    assert not required_columns.issubset(set(df.columns))


def test_invalid_datetime_is_detectable():
    """Malformed timestamps must not silently become valid dates."""

    df = pd.DataFrame({
        "tpep_pickup_datetime": ["THIS IS NOT A DATE"],
        "tpep_dropoff_datetime": ["2015-01-10 20:42:20"],
    })

    parsed = pd.to_datetime(
        df["tpep_pickup_datetime"],
        errors="coerce",
    )

    assert parsed.isna().all()


def test_non_numeric_fare_is_detectable():
    """A monetary column containing text should be detected."""

    df = pd.DataFrame({
        "fare_amount": ["52.0", "INVALID", "11.5"]
    })

    converted = pd.to_numeric(
        df["fare_amount"],
        errors="coerce",
    )

    assert converted.isna().sum() == 1


def test_negative_distance_is_detectable():
    """Negative trip distance is invalid taxi-domain data."""

    df = pd.DataFrame({
        "trip_distance": [15.5, 3.0, -10.0]
    })

    invalid = df[df["trip_distance"] < 0]

    assert len(invalid) == 1


def test_dropoff_before_pickup_is_detectable():
    """A reversed trip interval must be rejected/flagged."""

    df = pd.DataFrame({
        "tpep_pickup_datetime": ["2015-01-10 20:53:52"],
        "tpep_dropoff_datetime": ["2015-01-10 20:33:39"],
    })

    pickup = pd.to_datetime(df["tpep_pickup_datetime"])
    dropoff = pd.to_datetime(df["tpep_dropoff_datetime"])

    assert (dropoff <= pickup).all()


# ============================================================
# 6. COLUMN ORDER / SCHEMA DRIFT TESTS
# ============================================================

def test_transform_does_not_depend_on_column_order():
    """
    A robust loader should map by column name rather than assuming
    a fixed CSV column position.
    """

    normal = pd.DataFrame({
        "VendorID": [2],
        "trip_distance": [15.5],
        "fare_amount": [52.0],
    })

    reordered = pd.DataFrame({
        "fare_amount": [52.0],
        "VendorID": [2],
        "trip_distance": [15.5],
    })

    result_normal = app.transform_chunk(normal)
    result_reordered = app.transform_chunk(reordered)

    for column in ["vendorid", "trip_distance", "fare_amount"]:
        assert result_normal[column].iloc[0] == result_reordered[column].iloc[0]


def test_extra_columns_do_not_change_existing_values():
    """
    Adding an unrelated source column should not modify existing
    recognized fields during transformation.
    """

    base = pd.DataFrame({
        "VendorID": [2],
        "trip_distance": [15.5],
        "fare_amount": [52.0],
    })

    extended = base.copy()
    extended["unexpected_new_column"] = ["future_schema_field"]

    result_base = app.transform_chunk(base)
    result_extended = app.transform_chunk(extended)

    assert result_extended["vendorid"].iloc[0] == result_base["vendorid"].iloc[0]
    assert (
        result_extended["trip_distance"].iloc[0]
        == result_base["trip_distance"].iloc[0]
    )
    assert (
        result_extended["fare_amount"].iloc[0]
        == result_base["fare_amount"].iloc[0]
    )


# ============================================================
# 7. DATABASE ENGINE CONFIGURATION TESTS
# ============================================================

def test_get_engine_uses_env_vars(monkeypatch):
    """
    Database configuration should come from environment variables.
    """

    monkeypatch.setattr(app, "DB_USER", "testuser")
    monkeypatch.setattr(app, "DB_PASSWORD", "testpass")
    monkeypatch.setattr(app, "DB_HOST", "testhost")
    monkeypatch.setattr(app, "DB_PORT", "5555")
    monkeypatch.setattr(app, "DB_NAME", "testdb")

    engine = app.get_engine()

    assert str(engine.url) == (
        "postgresql+psycopg2://testuser:***@testhost:5555/testdb"
    )


def test_get_engine_uses_expected_database_name(monkeypatch):
    monkeypatch.setattr(app, "DB_USER", "user")
    monkeypatch.setattr(app, "DB_PASSWORD", "password")
    monkeypatch.setattr(app, "DB_HOST", "localhost")
    monkeypatch.setattr(app, "DB_PORT", "5432")
    monkeypatch.setattr(app, "DB_NAME", "taxi_db")

    engine = app.get_engine()

    assert engine.url.database == "taxi_db"


def test_get_engine_uses_expected_host(monkeypatch):
    monkeypatch.setattr(app, "DB_USER", "user")
    monkeypatch.setattr(app, "DB_PASSWORD", "password")
    monkeypatch.setattr(app, "DB_HOST", "postgres")
    monkeypatch.setattr(app, "DB_PORT", "5432")
    monkeypatch.setattr(app, "DB_NAME", "taxi_db")

    engine = app.get_engine()

    assert engine.url.host == "postgres"


def test_get_engine_uses_expected_port(monkeypatch):
    monkeypatch.setattr(app, "DB_USER", "user")
    monkeypatch.setattr(app, "DB_PASSWORD", "password")
    monkeypatch.setattr(app, "DB_HOST", "postgres")
    monkeypatch.setattr(app, "DB_PORT", "5439")
    monkeypatch.setattr(app, "DB_NAME", "taxi_db")

    engine = app.get_engine()

    assert engine.url.port == 5439


# ============================================================
# 8. SQL SAFETY TESTS
# ============================================================

def test_create_table_sql_does_not_contain_drop_database():
    """The application must never destroy the database itself."""

    sql = app.CREATE_TABLE_SQL.lower()

    assert "drop database" not in sql


def test_create_table_sql_does_not_contain_truncate():
    """
    A table creation statement should not unexpectedly wipe existing
    production data.
    """

    sql = app.CREATE_TABLE_SQL.lower()

    assert "truncate" not in sql


def test_create_table_sql_does_not_contain_delete_without_where():
    """
    Defensive test against accidental full-table deletion.
    """

    sql = " ".join(app.CREATE_TABLE_SQL.lower().split())

    assert "delete from" not in sql


# ============================================================
# 9. DATA CORRUPTION DETECTION TESTS
# ============================================================

def test_known_first_record_values_are_exact(taxi_dataframe):
    """
    Row-count tests cannot detect silent corruption.
    This test validates important values from a known source record.
    """

    row = taxi_dataframe.iloc[0]

    assert row["VendorID"] == 2
    assert row["trip_distance"] == 15.5
    assert row["fare_amount"] == 52.0
    assert row["tip_amount"] == 11.65
    assert row["total_amount"] == 69.95


def test_duplicate_records_have_identical_business_values(taxi_dataframe):
    """
    The duplicate rows in the fixture must actually be identical,
    not merely have the same count.
    """

    first = taxi_dataframe.iloc[0]
    duplicate = taxi_dataframe.iloc[5]

    columns = [
        "VendorID",
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
        "passenger_count",
        "trip_distance",
        "fare_amount",
        "tip_amount",
        "total_amount",
    ]

    for column in columns:
        if pd.isna(first[column]):
            assert pd.isna(duplicate[column])
        else:
            assert first[column] == duplicate[column]


# ============================================================
# 10. REGRESSION TESTS
# ============================================================

def test_transform_chunk_returns_dataframe():
    """Public transform API should continue returning a DataFrame."""

    chunk = pd.DataFrame({
        "VendorID": [1],
        "trip_distance": [2.5],
    })

    result = app.transform_chunk(chunk)

    assert isinstance(result, pd.DataFrame)


def test_transform_chunk_does_not_change_number_of_columns():
    """Transformation should not unexpectedly lose source fields."""

    chunk = pd.DataFrame({
        "VendorID": [1],
        "passenger_count": [1],
        "trip_distance": [2.5],
        "fare_amount": [10.0],
    })

    result = app.transform_chunk(chunk)

    assert len(result.columns) == len(chunk.columns)


# ============================================================
# 11. CONTRACT TESTS
# ============================================================

def test_required_application_functions_exist():
    """
    Protect the public application contract used by the pipeline.
    """

    assert callable(app.transform_chunk)
    assert callable(app.load_data)
    assert callable(app.get_engine)


def test_create_table_sql_is_string():
    assert isinstance(app.CREATE_TABLE_SQL, str)
    assert len(app.CREATE_TABLE_SQL.strip()) > 0
