import pandas as pd
import pytest

import app


def test_transform_chunk_lowercases_columns():
    chunk = pd.DataFrame({
        'VendorID': [1, 2],
        'passenger_count': [1, 2],
        'RatecodeID': [1, 1],
        'payment_type': [1, 2],
        'trip_distance': [1.2, 3.4],
    })
    result = app.transform_chunk(chunk)
    assert list(result.columns) == ['vendorid', 'passenger_count', 'ratecodeid', 'payment_type', 'trip_distance']


def test_transform_chunk_handles_nan_in_integer_columns():
    # passenger_count has a missing value, as real taxi data sometimes does.
    chunk = pd.DataFrame({
        'VendorID': [1, 2, 3],
        'passenger_count': [1, None, 3],
        'RatecodeID': [1, 1, 2],
        'payment_type': [1, 2, 1],
    })
    result = app.transform_chunk(chunk)

    # Should not raise, and should use the nullable Int64 dtype rather
    # than silently falling back to float64.
    assert str(result['passenger_count'].dtype) == 'Int64'
    assert result['passenger_count'].isna().sum() == 1
    assert result.loc[0, 'passenger_count'] == 1



def test_create_table_sql_defines_expected_columns():
    for column in [
        'vendorid', 'tpep_pickup_datetime', 'tpep_dropoff_datetime',
        'passenger_count', 'trip_distance', 'fare_amount', 'total_amount',
    ]:
        assert column in app.CREATE_TABLE_SQL.lower()


def test_load_data_raises_when_csv_missing(tmp_path):
    missing_path = tmp_path / 'does_not_exist.csv'
    with pytest.raises(FileNotFoundError):
        app.load_data(csv_path=str(missing_path), engine=object())


def test_get_engine_uses_env_vars(monkeypatch):
    monkeypatch.setattr(app, 'DB_USER', 'testuser')
    monkeypatch.setattr(app, 'DB_PASSWORD', 'testpass')
    monkeypatch.setattr(app, 'DB_HOST', 'testhost')
    monkeypatch.setattr(app, 'DB_PORT', '5555')
    monkeypatch.setattr(app, 'DB_NAME', 'testdb')

    engine = app.get_engine()
    assert str(engine.url) == 'postgresql+psycopg2://testuser:***@testhost:5555/testdb'