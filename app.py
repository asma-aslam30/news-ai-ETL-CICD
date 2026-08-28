import os
import pandas as pd
from sqlalchemy import create_engine, text

# lets test the CI/Cd pipeline
DB_HOST = os.environ.get('DB_HOST', 'postgres')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'postgres')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')
CSV_PATH = os.environ.get('CSV_PATH', 'yellow_tripdata_2015-01.csv')

CREATE_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS yellow_taxi_data (
    vendorid INTEGER,
    tpep_pickup_datetime TIMESTAMP,
    tpep_dropoff_datetime TIMESTAMP,
    passenger_count INTEGER,
    trip_distance DOUBLE PRECISION,
    pickup_longitude DOUBLE PRECISION,
    pickup_latitude DOUBLE PRECISION,
    ratecodeid INTEGER,
    store_and_fwd_flag TEXT,
    dropoff_longitude DOUBLE PRECISION,
    dropoff_latitude DOUBLE PRECISION,
    payment_type INTEGER,
    fare_amount DOUBLE PRECISION,
    extra DOUBLE PRECISION,
    mta_tax DOUBLE PRECISION,
    tip_amount DOUBLE PRECISION,
    tolls_amount DOUBLE PRECISION,
    improvement_surcharge DOUBLE PRECISION,
    total_amount DOUBLE PRECISION
)
'''

# Columns that should end up as nullable integers in Postgres.
# Pandas' "Int64" (capital I) is the nullable integer dtype - it tolerates
# NaNs, unlike plain int64, and won't leave stray ".0" floats behind.
INT_COLUMNS = ['vendorid', 'passenger_count', 'ratecodeid', 'payment_type']
DATE_COLUMNS = ['tpep_pickup_datetime', 'tpep_dropoff_datetime']


def get_engine():
    """Build a SQLAlchemy engine from the DB_* environment variables."""
    url = f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    return create_engine(url)


def create_table(engine):
    """Create the destination table if it doesn't already exist."""
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))


def transform_chunk(chunk):
    """Clean one raw CSV chunk so it's safe to insert into Postgres."""
    chunk = chunk.copy()
    chunk.columns = [c.lower() for c in chunk.columns]

    for col in INT_COLUMNS:
        if col not in chunk.columns:
            raise ValueError(
                f"Expected integer column '{col}' not found in this chunk. "
                f"Found columns: {sorted(chunk.columns)}. "
                f"This usually means a typo in INT_COLUMNS or a schema change "
                f"in the source CSV."
            )
        chunk[col] = chunk[col].astype('Int64')

    return chunk


def load_data(csv_path=None, engine=None, chunksize=10000):
    """Read the CSV in chunks, transform each chunk, and load it to Postgres."""
    csv_path = csv_path or CSV_PATH
    engine = engine or get_engine()

    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Could not find CSV at {csv_path}. "
            f"Place the taxi data CSV in the ./data folder next to docker-compose.yaml."
        )

    create_table(engine)

    total_rows = 0
    chunks = pd.read_csv(csv_path, chunksize=chunksize, parse_dates=DATE_COLUMNS)
    for i, chunk in enumerate(chunks, start=1):
        clean_chunk = transform_chunk(chunk)
        clean_chunk.to_sql('yellow_taxi_data', engine, if_exists='append', index=False)
        total_rows += len(clean_chunk)
        print(f'Inserted chunk {i} with {len(clean_chunk)} rows')

    print('All chunks inserted successfully.')
    return total_rows


if __name__ == '__main__':
    load_data()