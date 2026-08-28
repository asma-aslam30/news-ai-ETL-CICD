# NYC Yellow Taxi ETL Pipelinees

A Dockerized ETL pipeline that loads NYC Yellow Taxi trip data into PostgreSQL, wired into a full CI/CD workflow with GitHub Actions. Built as a teaching project covering practical DevOps and data engineering patterns end-to-end: containerization, automated testing, integration testing against a real database, and automated image publishing.

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
- [Running the Pipeline](#running-the-pipeline)
- [Running Tests Locally](#running-tests-locally)
- [CI/CD Overview](#cicd-overview)
- [Testing the CI/CD Pipeline Through Pytest](#testing-the-cicd-pipeline-through-pytest)
- [Branch Protection Setup](#branch-protection-setup)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)

## Architecture

```
CSV file (data/) --> app.py (pandas, chunked read) --> PostgreSQL --> pgAdmin (browse)
```

- **`app.py`** reads a CSV in chunks, lowercases/cleans column names, casts integer columns to pandas' nullable `Int64` dtype (so missing values don't force a float64 column and break the Postgres `INTEGER` schema), and inserts each chunk into a `yellow_taxi_data` table.
- **PostgreSQL** stores the loaded data.
- **pgAdmin** gives you a web UI to browse the database.
- **Docker Compose** wires all three services together, mounting the CSV in as a volume rather than baking it into the image (keeps the image small).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- Python 3.11 (only needed if you want to run tests or the app outside Docker)
- A GitHub account (for forking/pushing and using GitHub Actions)
- The taxi trip CSV, e.g. `yellow_tripdata_2015-01.csv`, downloaded from the [NYC Yellow Taxi Trip Data](https://www.kaggle.com/datasets/elemento/nyc-yellow-taxi-trip-data) 

## Local Setup

1. **Clone the repo**

   ```bash
   git clone <your-repo-url>
   cd <repo-folder>
   ```

2. **Add the data file**

   Create a `data/` folder in the project root and place your CSV inside it:

   ```bash
   mkdir -p data
   mv ~/Downloads/yellow_tripdata_2015-01.csv data/
   ```

   The `data/` folder is git-ignored on purpose — raw data files don't belong in version control.

3. **(Optional) Adjust environment variables**

   The `loader` service in `docker-compose.yaml` already sets sensible defaults (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `CSV_PATH`). Edit `docker-compose.yaml` directly if you want to point at a different CSV filename or change credentials.

## Running the Pipeline

Start everything with Docker Compose:

```bash
docker compose up --build
```

This will:

1. Start PostgreSQL and wait until it's healthy.
2. Build and run the `loader` container, which reads the CSV, creates the `yellow_taxi_data` table if it doesn't exist, and inserts the data in chunks.
3. Start pgAdmin at [http://localhost:5051](http://localhost:5051) (login: `admin@admin.com` / `root`) so you can browse the loaded data. Add a new server pointing at host `postgres`, port `5432`, database `postgres`, user `postgres`, password `postgres`.

To tear everything down (and optionally wipe the database volume):

```bash
docker compose down          # stop containers, keep data
docker compose down -v       # stop containers and delete the Postgres volume
```

## Running Tests Locally

The test suite (`test_app.py`) covers the pure-Python transform logic without needing a live database, plus a couple of integration-style checks.

1. Create a virtual environment and install dev dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```

2. Run the tests:

   ```bash
   pytest -v
   ```

   You should see tests covering:
   - Column lowercasing (`test_transform_chunk_lowercases_columns`)
   - Nullable integer handling for missing values (`test_transform_chunk_handles_nan_in_integer_columns`)
   - The `CREATE TABLE` SQL defining expected columns
   - `load_data` raising `FileNotFoundError` for a missing CSV
   - `get_engine` correctly building a connection URL from env vars


## CI/CD Overview

This repo uses a **two-branch strategy**:

| Branch | Workflow file | Trigger | What it does |
|---|---|---|---|
| `dev` | `.github/workflows/ci_dev.yml` | Push to `dev`, or PR targeting `dev` | Installs deps, runs `pytest -v`, runs a lint check for real errors only. **CI only** — nothing is built or published. |
| `main` | `.github/workflows/cd_prod.yml` | Push to `main`, or PR targeting `main` | Runs unit tests, then an **integration test** against a real Postgres service container, then (on `push` only) builds and pushes a Docker image to GHCR. |

### What the integration test actually does

The `integration-test` job in `cd_prod.yml` spins up a real PostgreSQL 16 container as a GitHub Actions *service*, runs `app.py` against the small fixture at `tests/fixtures/sample_trips.csv` (5 sample rows), and then queries the database directly to confirm all 5 rows landed in `yellow_taxi_data`. This proves the loader works end-to-end, not just that the transform function behaves correctly in isolation.

### What "build-and-push skipped" means

The `build-and-push` job only runs `if: github.event_name == 'push'`. On a pull request run, you'll see this job listed as **skipped** — that's expected, not a failure. Images are only published once code is actually merged into `main` and a real push event fires, so nothing gets published to the registry based on an unmerged PR.


## Testing the CI/CD Pipeline Through Pytest

You don't need to push code to see whether your pipeline logic is sound — most of it can be exercised locally first, then verified for real once pushed.

### Step 1 — Prove the unit tests pass locally

```bash
pip install -r requirements-dev.txt
pytest -v
```

This mirrors exactly what the `test` job runs in both `ci_dev.yml` and `cd_prod.yml`.


### Step 3 — Exercise CI on a feature branch

1. Create a feature branch off `dev`:

   ```bash
   git checkout -b feature/my-change dev
   ```

2. Make your change, commit, and push:

   ```bash
   git push origin feature/my-change
   ```

3. Open a pull request **into `dev`**. This triggers `ci_dev.yml`: pytest + lint. Watch the **Actions** tab in GitHub — the check must go green before merging (assuming branch protection is set up, see below).

### Step 4 — Exercise CD by merging to main

1. Open a pull request from `dev` **into `main`**. This triggers `cd_prod.yml`'s `test` and `integration-test` jobs (the real Postgres service container run). `build-and-push` will show as skipped on the PR — that's correct.
2. Once the checks pass and the PR is merged, the resulting `push` event to `main` re-runs `cd_prod.yml`, and this time `build-and-push` actually runs, publishing:
   - `ghcr.io/<owner>/<repo>/taxi-loader:latest`
   - `ghcr.io/<owner>/<repo>/taxi-loader:<commit-sha>`
3. Confirm the image published under your GitHub account/org's **Packages** tab.

## Branch Protection Setup

To make the CI/CD gates actually enforce anything, configure branch protection rules in GitHub:

1. Go to **Settings → Branches** in your repository.
2. Add a rule for `dev`:
   - Require status checks to pass before merging.
   - Select the `test` job from `ci_dev.yml` (may appear as `CI - dev branch / test`).
3. Add a rule for `main`:
   - Require status checks to pass before merging.
   - Select the `test` and `integration-test` jobs from `cd_prod.yml`.
   - Optionally require a pull request before merging, and require branches to be up to date.

With these in place, a feature branch can't merge into `dev` until pytest/lint are green, and `dev` can't merge into `main` until the full integration test against a real Postgres instance passes.

## Troubleshooting

- **`ghcr.io` push fails with an invalid reference / uppercase error** — GHCR requires lowercase image names. Make sure the workflow lowercases `github.repository` before using it in a tag.
- **CI fails immediately on `pip install -r requirements-dev.txt`** — check for exact filename matches. A hyphen vs. underscore mismatch (`requirements-dev.txt` vs `requirements_dev.txt`) will cause the install step to fail with a "file not found" error even though the file exists under a similar name.
- **`build-and-push` shows as skipped** — this is expected on pull request runs. It only runs on an actual `push` event to `main`, i.e. after a PR is merged.
- **Docker image is unexpectedly large** — make sure the CSV isn't being `COPY`'d into the image in the `Dockerfile`. Data should always be mounted in as a volume (see `docker-compose.yaml`), not baked into the image.
- **`passenger_count` insert fails with a type mismatch** — check that `transform_chunk` is casting integer columns to pandas' nullable `Int64` dtype (capital I), not the default `int64`, which can't represent missing values and will silently upcast to `float64`.

## Project Structure

```
.
├── app.py                          # ETL logic: extract, transform, load
├── test_app.py                     # Unit tests for the app's functions
├── requirements.txt                # Runtime dependencies
├── requirements-dev.txt            # Runtime + pytest, for CI
├── Dockerfile                      # Loader image definition
├── docker-compose.yaml             # Postgres + loader + pgAdmin
├── .gitignore
├── tests/
│   └── fixtures/
│       └── sample_trips.csv        # Small fixture used by the integration test
└── .github/
    └── workflows/
        ├── ci_dev.yml               # CI: runs on dev (pytest + lint)
        └── cd_prod.yml              # CD: runs on main (tests + integration + GHCR push)
```