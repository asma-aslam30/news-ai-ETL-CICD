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
 
import os
from unittest.mock import MagicMock

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

import app


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def taxi_dataframe():
    """
    The exact 10-row NYC Taxi dataset supplied for this project.
    Rows 6-10 intentionally duplicate rows 1-5.
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

        "RateCodeID": [1] * 10,

        "store_and_fwd_flag": ["N"] * 10,

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

        "extra": [0.5] * 10,
        "mta_tax": [0.5] * 10,

        "tip_amount": [
            11.65, 2.0, 0.0, 0.0, 0.0,
            11.65, 2.0, 0.0, 0.0, 0.0
        ],

        "tolls_amount": [0.0] * 10,
        "improvement_surcharge": [0.3] * 10,

        "total_amount": [
            69.95, 14.8, 5.8, 28.3, 7.3,
            69.95, 14.8, 5.8, 28.3, 7.3
        ],
    })


@pytest.fixture
def sample_csv(tmp_path, taxi_dataframe):
    """Create a temporary CSV using the supplied taxi dataset."""

    path = tmp_path / "sample_trips.csv"

    taxi_dataframe.to_csv(path, index=False)

    return path


@pytest.fixture
def sqlite_engine():
    """
    SQLite engine used for isolated tests that don't require PostgreSQL.

    PostgreSQL-specific integration tests remain separate.
    """

    return create_engine("sqlite:///:memory:")


# ============================================================
# 1. TRANSFORMATION TESTS
# ============================================================

def test_transform_chunk_lowercases_columns():
    chunk = pd.DataFrame({
        "VendorID": [1, 2],
        "passenger_count": [1, 2],
        "RatecodeID": [1, 1],
        "payment_type": [1, 2],
        "trip_distance": [1.2, 3.4],
    })

    result = app.transform_chunk(chunk)

    assert list(result.columns) == [
        "vendorid",
        "passenger_count",
        "ratecodeid",
        "payment_type",
        "trip_distance",
    ]


def test_transform_chunk_handles_nan_in_integer_columns():
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


def test_transform_chunk_handles_nan_vendorid():
    chunk = pd.DataFrame({
        "VendorID": [1, None, 2],
        "passenger_count": [1, 2, 3],
        "RatecodeID": [1, 1, 1],
        "payment_type": [1, 2, 1],
    })

    result = app.transform_chunk(chunk)

    assert str(result["vendorid"].dtype) == "Int64"
    assert result["vendorid"].isna().sum() == 1


def test_transform_chunk_handles_nan_ratecodeid():
    chunk = pd.DataFrame({
        "VendorID": [1, 2],
        "passenger_count": [1, 2],
        "RatecodeID": [1, None],
        "payment_type": [1, 2],
    })

    result = app.transform_chunk(chunk)

    assert str(result["ratecodeid"].dtype) == "Int64"
    assert result["ratecodeid"].isna().sum() == 1


def test_transform_chunk_handles_nan_payment_type():
    chunk = pd.DataFrame({
        "VendorID": [1, 2],
        "passenger_count": [1, 2],
        "RatecodeID": [1, 1],
        "payment_type": [1, None],
    })

    result = app.transform_chunk(chunk)

    assert str(result["payment_type"].dtype) == "Int64"
    assert result["payment_type"].isna().sum() == 1


def test_transform_chunk_preserves_row_count():
    chunk = pd.DataFrame({
        "VendorID": [1, 2, 3, 4, 5],
        "passenger_count": [1, 2, 1, 3, 2],
        "RatecodeID": [1, 1, 1, 1, 2],
        "payment_type": [1, 2, 1, 2, 1],
    })

    result = app.transform_chunk(chunk)

    assert len(result) == 5


def test_transform_chunk_preserves_duplicate_rows():
    chunk = pd.DataFrame({
        "VendorID": [2, 2],
        "passenger_count": [1, 1],
        "RatecodeID": [1, 1],
        "payment_type": [1, 1],
    })

    result = app.transform_chunk(chunk)

    assert len(result) == 2
    assert result.iloc[0].equals(result.iloc[1])


def test_transform_chunk_does_not_modify_original_dataframe():
    chunk = pd.DataFrame({
        "VendorID": [1, 2],
        "passenger_count": [1, 2],
        "RatecodeID": [1, 1],
        "payment_type": [1, 2],
    })

    original = chunk.copy(deep=True)

    app.transform_chunk(chunk)

    pd.testing.assert_frame_equal(chunk, original)


def test_transform_chunk_handles_empty_dataframe():
    chunk = pd.DataFrame(
        columns=[
            "VendorID",
            "passenger_count",
            "RatecodeID",
            "payment_type",
        ]
    )

    result = app.transform_chunk(chunk)

    assert result.empty
    assert len(result) == 0


def test_transform_chunk_mixed_case_columns():
    chunk = pd.DataFrame({
        "VeNdOrId": [1],
        "PASSENGER_COUNT": [1],
        "RateCodeID": [1],
        "PaYmEnT_TyPe": [1],
    })

    result = app.transform_chunk(chunk)

    assert "vendorid" in result.columns
    assert "passenger_count" in result.columns
    assert "ratecodeid" in result.columns
    assert "payment_type" in result.columns


# ============================================================
# 2. REQUIRED COLUMN / SCHEMA VALIDATION
# ============================================================

def test_transform_chunk_raises_when_vendorid_missing():
    chunk = pd.DataFrame({
        "passenger_count": [1],
        "RateCodeID": [1],
        "payment_type": [1],
    })

    with pytest.raises(ValueError, match="vendorid"):
        app.transform_chunk(chunk)


def test_transform_chunk_raises_when_passenger_count_missing():
    chunk = pd.DataFrame({
        "VendorID": [1],
        "RateCodeID": [1],
        "payment_type": [1],
    })

    with pytest.raises(ValueError, match="passenger_count"):
        app.transform_chunk(chunk)


def test_transform_chunk_raises_when_ratecodeid_missing():
    chunk = pd.DataFrame({
        "VendorID": [1],
        "passenger_count": [1],
        "payment_type": [1],
    })

    with pytest.raises(ValueError, match="ratecodeid"):
        app.transform_chunk(chunk)


def test_transform_chunk_raises_when_payment_type_missing():
    chunk = pd.DataFrame({
        "VendorID": [1],
        "passenger_count": [1],
        "RatecodeID": [1],
    })

    with pytest.raises(ValueError, match="payment_type"):
        app.transform_chunk(chunk)


def test_transform_chunk_error_contains_available_columns():
    chunk = pd.DataFrame({
        "VendorID": [1],
        "passenger_count": [1],
        "RateCodeID": [1],
    })

    with pytest.raises(ValueError) as exc:
        app.transform_chunk(chunk)

    message = str(exc.value).lower()

    assert "payment_type" in message
    assert "found columns" in message


# ============================================================
# 3. TABLE DEFINITION TESTS
# ============================================================

def test_create_table_sql_defines_expected_columns():
    for column in [
        "vendorid",
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
        "passenger_count",
        "trip_distance",
        "fare_amount",
        "total_amount",
    ]:
        assert column in app.CREATE_TABLE_SQL.lower()


def test_create_table_sql_contains_all_nyc_taxi_columns():
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
        assert column in sql


def test_create_table_sql_uses_expected_table_name():
    assert "yellow_taxi_data" in app.CREATE_TABLE_SQL.lower()


def test_create_table_sql_is_idempotent():
    assert "create table if not exists" in app.CREATE_TABLE_SQL.lower()


def test_create_table_sql_does_not_drop_database():
    assert "drop database" not in app.CREATE_TABLE_SQL.lower()


def test_create_table_sql_does_not_truncate():
    assert "truncate" not in app.CREATE_TABLE_SQL.lower()


def test_create_table_sql_does_not_delete_data():
    assert "delete from" not in app.CREATE_TABLE_SQL.lower()


def test_create_table_sql_is_string():
    assert isinstance(app.CREATE_TABLE_SQL, str)
    assert app.CREATE_TABLE_SQL.strip()


# ============================================================
# 4. DATASET VALIDATION
# ============================================================

def test_dataset_has_expected_row_count(taxi_dataframe):
    assert len(taxi_dataframe) == 10


def test_dataset_has_five_duplicate_rows(taxi_dataframe):
    assert taxi_dataframe.duplicated().sum() == 5


def test_dataset_has_five_unique_rows(taxi_dataframe):
    assert len(taxi_dataframe.drop_duplicates()) == 5


def test_dataset_has_expected_vendor_distribution(taxi_dataframe):
    counts = taxi_dataframe["VendorID"].value_counts(dropna=False)

    assert counts[1] == 4
    assert counts[2] == 4
    assert taxi_dataframe["VendorID"].isna().sum() == 2


def test_dataset_has_expected_payment_distribution(taxi_dataframe):
    counts = taxi_dataframe["payment_type"].value_counts()

    assert counts[1] == 6
    assert counts[2] == 4


def test_dataset_has_expected_passenger_null_count(taxi_dataframe):
    assert taxi_dataframe["passenger_count"].isna().sum() == 2


def test_trip_distance_is_non_negative(taxi_dataframe):
    assert (taxi_dataframe["trip_distance"] >= 0).all()


def test_fare_amount_is_non_negative(taxi_dataframe):
    assert (taxi_dataframe["fare_amount"] >= 0).all()


def test_tip_amount_is_non_negative(taxi_dataframe):
    assert (taxi_dataframe["tip_amount"] >= 0).all()


def test_total_amount_is_not_less_than_fare(taxi_dataframe):
    assert (
        taxi_dataframe["total_amount"]
        >= taxi_dataframe["fare_amount"]
    ).all()


def test_pickup_coordinates_are_reasonable(taxi_dataframe):
    assert taxi_dataframe["pickup_longitude"].between(-75, -72).all()
    assert taxi_dataframe["pickup_latitude"].between(40, 42).all()


def test_dropoff_coordinates_are_reasonable(taxi_dataframe):
    assert taxi_dataframe["dropoff_longitude"].between(-75, -72).all()
    assert taxi_dataframe["dropoff_latitude"].between(40, 42).all()


def test_store_and_forward_flag_is_valid(taxi_dataframe):
    assert set(
        taxi_dataframe["store_and_fwd_flag"].dropna()
    ) <= {"Y", "N"}


def test_payment_type_values_are_valid(taxi_dataframe):
    assert set(
        taxi_dataframe["payment_type"].dropna()
    ) <= {1, 2, 3, 4}


# ============================================================
# 5. DATETIME / BUSINESS LOGIC
# ============================================================

def test_all_dropoffs_are_after_pickups(taxi_dataframe):
    pickup = pd.to_datetime(
        taxi_dataframe["tpep_pickup_datetime"]
    )

    dropoff = pd.to_datetime(
        taxi_dataframe["tpep_dropoff_datetime"]
    )

    assert (dropoff > pickup).all()


def test_all_trip_durations_are_positive(taxi_dataframe):
    pickup = pd.to_datetime(
        taxi_dataframe["tpep_pickup_datetime"]
    )

    dropoff = pd.to_datetime(
        taxi_dataframe["tpep_dropoff_datetime"]
    )

    duration = (dropoff - pickup).dt.total_seconds()

    assert (duration > 0).all()


def test_first_trip_duration_is_exact():
    pickup = pd.Timestamp("2015-01-10 20:33:39")
    dropoff = pd.Timestamp("2015-01-10 20:53:52")

    assert (dropoff - pickup).total_seconds() == 1213


def test_reversed_datetime_is_detectable():
    pickup = pd.Timestamp("2015-01-10 20:53:52")
    dropoff = pd.Timestamp("2015-01-10 20:33:39")

    assert dropoff <= pickup


# ============================================================
# 6. EXACT DATA INTEGRITY
# ============================================================

def test_known_first_record_is_exact(taxi_dataframe):
    row = taxi_dataframe.iloc[0]

    assert row["VendorID"] == 2
    assert row["trip_distance"] == 15.5
    assert row["fare_amount"] == 52.0
    assert row["tip_amount"] == 11.65
    assert row["total_amount"] == 69.95


def test_known_trip_distances_are_preserved(taxi_dataframe):
    expected = [15.5, 3.0, 0.5, 9.0, 1.2]

    actual = taxi_dataframe["trip_distance"].iloc[:5].tolist()

    assert actual == expected


def test_known_total_amounts_are_preserved(taxi_dataframe):
    expected = [69.95, 14.8, 5.8, 28.3, 7.3]

    actual = taxi_dataframe["total_amount"].iloc[:5].tolist()

    assert actual == expected


def test_duplicate_business_records_are_identical(taxi_dataframe):
    first = taxi_dataframe.iloc[0]
    duplicate = taxi_dataframe.iloc[5]

    for column in [
        "VendorID",
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
        "passenger_count",
        "trip_distance",
        "fare_amount",
        "tip_amount",
        "total_amount",
    ]:
        if pd.isna(first[column]):
            assert pd.isna(duplicate[column])
        else:
            assert first[column] == duplicate[column]


# ============================================================
# 7. INPUT FAILURE TESTS
# ============================================================

def test_load_data_raises_when_csv_missing(tmp_path):
    missing_path = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError):
        app.load_data(
            csv_path=str(missing_path),
            engine=object(),
        )


def test_missing_csv_does_not_create_file(tmp_path):
    missing_path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError):
        app.load_data(
            csv_path=str(missing_path),
            engine=object(),
        )

    assert not missing_path.exists()


def test_empty_csv_is_detectable(tmp_path):
    path = tmp_path / "empty.csv"

    path.write_text("", encoding="utf-8")

    assert path.exists()
    assert path.stat().st_size == 0


def test_header_only_csv_is_detectable(tmp_path):
    path = tmp_path / "header.csv"

    path.write_text(
        "VendorID,tpep_pickup_datetime,"
        "tpep_dropoff_datetime,passenger_count,trip_distance\n",
        encoding="utf-8",
    )

    df = pd.read_csv(path)

    assert df.empty
    assert len(df.columns) == 5


def test_missing_required_source_column_is_detectable(tmp_path):
    path = tmp_path / "missing_column.csv"

    path.write_text(
        "VendorID,tpep_pickup_datetime,tpep_dropoff_datetime\n"
        "1,2015-01-10 20:33:38,2015-01-10 20:42:20\n",
        encoding="utf-8",
    )

    df = pd.read_csv(path)

    required = {
        "VendorID",
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
        "passenger_count",
        "trip_distance",
    }

    assert not required.issubset(df.columns)


def test_invalid_datetime_is_detectable():
    df = pd.DataFrame({
        "tpep_pickup_datetime": ["NOT_A_DATE"]
    })

    parsed = pd.to_datetime(
        df["tpep_pickup_datetime"],
        errors="coerce",
    )

    assert parsed.isna().all()


def test_non_numeric_fare_is_detectable():
    df = pd.DataFrame({
        "fare_amount": ["52.0", "INVALID", "11.5"]
    })

    converted = pd.to_numeric(
        df["fare_amount"],
        errors="coerce",
    )

    assert converted.isna().sum() == 1


def test_negative_distance_is_detectable():
    df = pd.DataFrame({
        "trip_distance": [15.5, 3.0, -1.0]
    })

    assert (df["trip_distance"] < 0).sum() == 1


# ============================================================
# 8. SCHEMA DRIFT / COLUMN ORDER
# ============================================================

def test_column_order_does_not_change_values():
    normal = pd.DataFrame({
        "VendorID": [2],
        "passenger_count": [1],
        "RateCodeID": [1],
        "payment_type": [1],
        "trip_distance": [15.5],
    })

    reordered = pd.DataFrame({
        "trip_distance": [15.5],
        "payment_type": [1],
        "VendorID": [2],
        "RateCodeID": [1],
        "passenger_count": [1],
    })

    result1 = app.transform_chunk(normal)
    result2 = app.transform_chunk(reordered)

    for column in [
        "vendorid",
        "passenger_count",
        "ratecodeid",
        "payment_type",
        "trip_distance",
    ]:
        assert result1[column].iloc[0] == result2[column].iloc[0]


def test_extra_column_does_not_corrupt_known_values():
    base = pd.DataFrame({
        "VendorID": [2],
        "passenger_count": [1],
        "RateCodeID": [1],
        "payment_type": [1],
        "trip_distance": [15.5],
    })

    extended = base.copy()
    extended["new_future_column"] = ["future"]

    result = app.transform_chunk(extended)

    assert result["vendorid"].iloc[0] == 2
    assert result["passenger_count"].iloc[0] == 1
    assert result["trip_distance"].iloc[0] == 15.5


# ============================================================
# 9. DATABASE ENGINE CONFIGURATION
# ============================================================

def test_get_engine_uses_env_vars(monkeypatch):
    monkeypatch.setattr(app, "DB_USER", "testuser")
    monkeypatch.setattr(app, "DB_PASSWORD", "testpass")
    monkeypatch.setattr(app, "DB_HOST", "testhost")
    monkeypatch.setattr(app, "DB_PORT", "5555")
    monkeypatch.setattr(app, "DB_NAME", "testdb")

    engine = app.get_engine()

    assert str(engine.url) == (
        "postgresql+psycopg2://testuser:***@testhost:5555/testdb"
    )


def test_get_engine_uses_expected_database(monkeypatch):
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
# 10. APPLICATION CONTRACT / REGRESSION
# ============================================================

def test_required_application_functions_exist():
    assert callable(app.transform_chunk)
    assert callable(app.load_data)
    assert callable(app.get_engine)
    assert callable(app.create_table)


def test_transform_chunk_returns_dataframe():
    chunk = pd.DataFrame({
        "VendorID": [1],
        "passenger_count": [1],
        "RateCodeID": [1],
        "payment_type": [1],
    })

    result = app.transform_chunk(chunk)

    assert isinstance(result, pd.DataFrame)


def test_transform_chunk_preserves_column_count():
    chunk = pd.DataFrame({
        "VendorID": [1],
        "passenger_count": [1],
        "RateCodeID": [1],
        "payment_type": [1],
        "trip_distance": [2.5],
    })

    result = app.transform_chunk(chunk)

    assert len(result.columns) == len(chunk.columns)


# ============================================================
# 11. LOAD_DATA MOCKED BEHAVIOR
# ============================================================

def test_load_data_returns_total_rows(sample_csv):
    """
    Mock the database operations so this test verifies the loader's
    chunking/counting behavior without requiring PostgreSQL.
    """

    engine = MagicMock()

    result = app.load_data(
        csv_path=str(sample_csv),
        engine=engine,
        chunksize=5,
    )

    assert result == 10


def test_load_data_processes_multiple_chunks(sample_csv):
    """
    10 rows / chunksize 5 = exactly two chunks.
    """

    engine = MagicMock()

    app.load_data(
        csv_path=str(sample_csv),
        engine=engine,
        chunksize=5,
    )

    # create_table uses engine.begin()
    assert engine.begin.called


def test_load_data_with_chunk_size_one_counts_every_row(sample_csv):
    engine = MagicMock()

    result = app.load_data(
        csv_path=str(sample_csv),
        engine=engine,
        chunksize=1,
    )

    assert result == 10


def test_load_data_empty_dataset_returns_zero(tmp_path):
    path = tmp_path / "empty_with_header.csv"

    path.write_text(
        "VendorID,tpep_pickup_datetime,tpep_dropoff_datetime,"
        "passenger_count,trip_distance,RateCodeID,payment_type\n",
        encoding="utf-8",
    )

    engine = MagicMock()

    result = app.load_data(
        csv_path=str(path),
        engine=engine,
    )

    assert result == 0


# ============================================================
# 12. EXPERT: CHUNK FAILURE PROPAGATION
# ============================================================

def test_load_data_stops_when_transform_chunk_fails(sample_csv, monkeypatch):
    """
    If transformation of a later chunk fails, the exception must not
    be silently swallowed.
    """

    engine = MagicMock()

    original_transform = app.transform_chunk
    call_count = {"value": 0}

    def failing_transform(chunk):
        call_count["value"] += 1

        if call_count["value"] == 2:
            raise ValueError("Simulated transformation failure")

        return original_transform(chunk)

    monkeypatch.setattr(
        app,
        "transform_chunk",
        failing_transform,
    )

    with pytest.raises(ValueError, match="Simulated transformation failure"):
        app.load_data(
            csv_path=str(sample_csv),
            engine=engine,
            chunksize=5,
        )


def test_load_data_stops_when_to_sql_fails(sample_csv):
    """
    Simulate database insertion failure.
    The loader should propagate the database exception rather than
    reporting successful completion.
    """

    engine = MagicMock()

    failing_dataframe = MagicMock()

    # This test uses a monkeypatch on pandas DataFrame.to_sql below.
    original_to_sql = pd.DataFrame.to_sql

    def failing_to_sql(self, *args, **kwargs):
        raise RuntimeError("Simulated database failure")

    try:
        pd.DataFrame.to_sql = failing_to_sql

        with pytest.raises(RuntimeError, match="Simulated database failure"):
            app.load_data(
                csv_path=str(sample_csv),
                engine=engine,
                chunksize=5,
            )
    finally:
        pd.DataFrame.to_sql = original_to_sql


# ============================================================
# 13. EXPERT: LARGE CHUNK / SMALL CHUNK CONSISTENCY
# ============================================================

def test_chunk_size_does_not_change_total_result(sample_csv):
    engine1 = MagicMock()
    engine2 = MagicMock()

    result_small = app.load_data(
        csv_path=str(sample_csv),
        engine=engine1,
        chunksize=1,
    )

    result_large = app.load_data(
        csv_path=str(sample_csv),
        engine=engine2,
        chunksize=1000,
    )

    assert result_small == result_large == 10


def test_chunk_size_two_produces_correct_total(sample_csv):
    engine = MagicMock()

    result = app.load_data(
        csv_path=str(sample_csv),
        engine=engine,
        chunksize=2,
    )

    assert result == 10


# ============================================================
# 14. EXPERT: IDEMPOTENCY / RETRY BEHAVIOR
# ============================================================

def test_current_loader_is_not_idempotent_on_retry(sample_csv):
    """
    IMPORTANT:
    This documents the CURRENT implementation.

    Because load_data() uses:
        if_exists='append'

    running the same CSV twice results in the rows being inserted twice.

    This test intentionally describes current behavior so that a future
    idempotency change can be detected as a behavioral change.
    """

    calls = []

    original_to_sql = pd.DataFrame.to_sql

    def capture_to_sql(self, name, con, if_exists="fail", index=True, **kwargs):
        calls.append({
            "rows": len(self),
            "name": name,
            "if_exists": if_exists,
        })

    try:
        pd.DataFrame.to_sql = capture_to_sql

        engine = MagicMock()

        first = app.load_data(
            csv_path=str(sample_csv),
            engine=engine,
            chunksize=5,
        )

        second = app.load_data(
            csv_path=str(sample_csv),
            engine=engine,
            chunksize=5,
        )

    finally:
        pd.DataFrame.to_sql = original_to_sql

    assert first == 10
    assert second == 10

    # Two executions * two chunks = four append operations.
    assert len(calls) == 4

    assert all(
        call["if_exists"] == "append"
        for call in calls
    )


# ============================================================
# 15. EXPERT: CONCURRENT EXECUTION DOCUMENTATION
# ============================================================

def test_concurrent_execution_requires_database_level_protection():
    """
    The current CREATE TABLE schema has no PRIMARY KEY/UNIQUE constraint.

    Therefore two simultaneous executions can append the same dataset.

    This test documents that limitation rather than pretending the
    current implementation provides exactly-once semantics.
    """

    sql = app.CREATE_TABLE_SQL.lower()

    has_unique_protection = (
        "primary key" in sql
        or "unique" in sql
    )

    if not has_unique_protection:
        pytest.skip(
            "Current schema has no PRIMARY KEY/UNIQUE protection. "
            "Concurrent duplicate prevention is not implemented."
        )

    assert has_unique_protection


# ============================================================
# 16. EXPERT: FINANCIAL PRECISION
# ============================================================

def test_financial_values_preserve_decimal_information(taxi_dataframe):
    """
    Verify that values such as 11.65 and 69.95 are represented
    exactly in the source dataframe.

    Note:
    The production schema currently uses DOUBLE PRECISION, so this
    test validates source-level precision, not PostgreSQL NUMERIC
    semantics.
    """

    assert taxi_dataframe.loc[0, "tip_amount"] == 11.65
    assert taxi_dataframe.loc[0, "total_amount"] == 69.95
    assert taxi_dataframe.loc[1, "fare_amount"] == 11.5


def test_financial_total_relationship(taxi_dataframe):
    """
    Basic financial integrity relationship.
    """

    calculated_minimum = (
        taxi_dataframe["fare_amount"]
        + taxi_dataframe["mta_tax"]
        + taxi_dataframe["improvement_surcharge"]
    )

    assert (
        taxi_dataframe["total_amount"]
        >= calculated_minimum
    ).all()


# ============================================================
# 17. EXPERT: ENCODING ROBUSTNESS
# ============================================================

def test_utf8_csv_can_be_read(tmp_path):
    """
    Verify that the CSV ingestion layer can handle UTF-8 content.

    This uses the same CSV structure but adds Unicode text to the
    text column.
    """

    path = tmp_path / "unicode.csv"

    path.write_text(
        "VendorID,passenger_count,RateCodeID,payment_type,"
        "store_and_fwd_flag\n"
        "1,1,1,1,کراچی\n",
        encoding="utf-8",
    )

    df = pd.read_csv(path)

    assert df.loc[0, "store_and_fwd_flag"] == "کراچی"


# ============================================================
# 18. EXPERT: RESOURCE / CHUNKING
# ============================================================

def test_loader_uses_chunked_reading(sample_csv, monkeypatch):
    """
    Verify that load_data actually requests chunked CSV reading.

    This is important because the loader is designed for datasets
    much larger than memory.
    """

    original_read_csv = pd.read_csv
    captured = {}

    def tracked_read_csv(*args, **kwargs):
        captured["chunksize"] = kwargs.get("chunksize")
        return original_read_csv(*args, **kwargs)

    monkeypatch.setattr(
        pd,
        "read_csv",
        tracked_read_csv,
    )

    engine = MagicMock()

    app.load_data(
        csv_path=str(sample_csv),
        engine=engine,
        chunksize=3,
    )

    assert captured["chunksize"] == 3


def test_loader_does_not_require_entire_dataset_at_once(sample_csv):
    """
    Small chunks should still successfully process the complete dataset.
    """

    engine = MagicMock()

    result = app.load_data(
        csv_path=str(sample_csv),
        engine=engine,
        chunksize=1,
    )

    assert result == 10


# ============================================================
# 19. EXPERT: SQL CONNECTION FAILURE
# ============================================================

def test_create_table_propagates_database_failure():
    """
    If PostgreSQL rejects CREATE TABLE, the error should propagate.
    """

    engine = MagicMock()

    connection = MagicMock()

    connection.execute.side_effect = RuntimeError(
        "database connection failed"
    )

    context_manager = MagicMock()
    context_manager.__enter__.return_value = connection
    context_manager.__exit__.return_value = False

    engine.begin.return_value = context_manager

    with pytest.raises(RuntimeError, match="database connection failed"):
        app.create_table(engine)


def test_create_table_uses_transaction():
    """
    create_table() must use engine.begin(), which provides transactional
    connection handling.
    """

    engine = MagicMock()

    context_manager = MagicMock()

    context_manager.__enter__.return_value = MagicMock()
    context_manager.__exit__.return_value = False

    engine.begin.return_value = context_manager

    app.create_table(engine)

    engine.begin.assert_called_once()


# ============================================================
# 20. EXPERT: DATABASE INSERT CONTRACT
# ============================================================

def test_load_data_uses_append_mode(sample_csv):
    """
    Current loader intentionally appends each chunk.
    """

    calls = []

    original_to_sql = pd.DataFrame.to_sql

    def capture_to_sql(
        self,
        name,
        con,
        if_exists="fail",
        index=True,
        **kwargs
    ):
        calls.append({
            "name": name,
            "if_exists": if_exists,
            "index": index,
            "rows": len(self),
        })

    try:
        pd.DataFrame.to_sql = capture_to_sql

        engine = MagicMock()

        app.load_data(
            csv_path=str(sample_csv),
            engine=engine,
            chunksize=5,
        )

    finally:
        pd.DataFrame.to_sql = original_to_sql

    assert len(calls) == 2

    for call in calls:
        assert call["name"] == "yellow_taxi_data"
        assert call["if_exists"] == "append"
        assert call["index"] is False


def test_load_data_inserts_all_chunks(sample_csv):
    inserted_rows = []

    original_to_sql = pd.DataFrame.to_sql

    def capture_to_sql(
        self,
        name,
        con,
        if_exists="fail",
        index=True,
        **kwargs
    ):
        inserted_rows.append(len(self))

    try:
        pd.DataFrame.to_sql = capture_to_sql

        engine = MagicMock()

        result = app.load_data(
            csv_path=str(sample_csv),
            engine=engine,
            chunksize=3,
        )

    finally:
        pd.DataFrame.to_sql = original_to_sql

    assert result == 10
    assert sum(inserted_rows) == 10
    assert inserted_rows == [3, 3, 3, 1]


# ============================================================
# 21. EXPERT: PROCESSING ORDER
# ============================================================

def test_create_table_happens_before_loading(sample_csv, monkeypatch):
    events = []

    def fake_create_table(engine):
        events.append("create_table")

    original_to_sql = pd.DataFrame.to_sql

    def fake_to_sql(self, *args, **kwargs):
        events.append("insert")

    monkeypatch.setattr(
        app,
        "create_table",
        fake_create_table,
    )

    monkeypatch.setattr(
        pd.DataFrame,
        "to_sql",
        fake_to_sql,
    )

    engine = MagicMock()

    app.load_data(
        csv_path=str(sample_csv),
        engine=engine,
        chunksize=5,
    )

    assert events[0] == "create_table"
    assert "insert" in events


# ============================================================
# 22. FINAL CONTRACT CHECK
# ============================================================

def test_load_data_returns_integer(sample_csv):
    engine = MagicMock()

    result = app.load_data(
        csv_path=str(sample_csv),
        engine=engine,
        chunksize=5,
    )

    assert isinstance(result, int)


def test_default_configuration_values_exist():
    assert app.DB_HOST
    assert app.DB_PORT
    assert app.DB_NAME
    assert app.DB_USER
    assert app.DB_PASSWORD
    assert app.CSV_PATH
