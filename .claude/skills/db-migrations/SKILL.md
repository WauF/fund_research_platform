---
name: db-migrations
description: Rules for database schema changes and for rollback. Read this skill before you do one of these tasks - change backend/storage/models.py or backend/migrations/; write an Alembic migration; add, delete, or rename a table or a column; add an enum or a constraint; write a data migration; do a rollback (alembic downgrade or a restore from a backup).
---

# Database migrations and rollback

## Purpose

You must be able to return the system to a previous version manually. Data loss must not occur.
If data loss is not possible to prevent, the team must know about it before the change.

A code rollback is easy: you change the image tag. A database does not return to a previous state
automatically. Only migrations move the database schema forward or back. The rules in this skill
make sure that this movement is always possible.

## How this repository operates

| Item | Location or procedure |
| :--- | :--- |
| Tables (SQLAlchemy models) | `backend/storage/models.py` |
| Migrations | `backend/migrations/versions/NNNN_*.py` |
| Migration run | The `migrate` service in `docker-compose.yml` runs `alembic upgrade head`. The `api` service starts only after `migrate` stops with exit code 0. |
| Version | `APP_VERSION` is the image tag. The migration files are in the image. |
| Tests | `backend/tests/test_migrations.py` uses SQLite. The CI `docker` job does a migration round trip on real Postgres. |

Know these two facts before a rollback. We tested both facts.

1. An image knows only the migrations that are in that image. An old image does not know a newer
   revision in the database. Then the `migrate` service stops with the error
   `Can't locate revision identified by '0002'`, and the `api` service does not start. Because of
   this, `APP_VERSION=<old> docker compose up -d` alone does not operate after a version with a
   migration.
2. The `downgrade()` code is only in the new image. To move the database back, do the downgrade
   with the **new** image first. Then start the old image.

## Rules

### Rule 1: Change the schema only with a migration

- Do not change the schema manually with `psql` (`ALTER TABLE`, `CREATE INDEX`, or other
  commands). A manual change is not in a migration. A rollback does not remove it. Then the
  environments become different.
- Use `Base.metadata.create_all()` only in tests.
- Put the model change and its migration in the same PR. If a migration is not there,
  `test_migrations_match_models` shows an error.

### Rule 2: Write a correct `downgrade()` for each migration

- Do not write `pass` or `raise NotImplementedError` in `downgrade()`.
- Make the downgrade do the opposite of the upgrade. The downgrade must delete each table, index,
  constraint, and type that the upgrade creates.
- The tests and CI do this round trip automatically: `upgrade head`, `downgrade base`,
  `upgrade head`.
- A downgrade can delete data. For example, it can remove a column that the upgrade added. In this
  condition, write a `DATA LOSS:` line in the docstring of the migration. Also write it in the PR
  description. A data loss can be acceptable. A data loss that the team does not know about is not
  acceptable.

### Rule 3: Do not change a merged migration

A migration in `main` already ran on other computers and on the server. A change to the file does
not change these databases. It only makes the code and the databases different. To correct an
error, write a **new** migration.

### Rule 4: Keep one head and use sequential numbers

```bash
cd backend
uv run alembic revision --autogenerate --rev-id 0002 -m "create holdings"
```

- Set `--rev-id` to the next 4-digit number.
- Make sure that `uv run alembic heads` shows one line. A test also does a check of this.
- Two PRs can use the same number at the same time, for example `0002`. In this condition, the PR
  that merges into `main` second must use the number `0003`. Change the file name. Set
  `revision = "0003"` and `down_revision = "0002"`.
- Do not use `alembic merge`. A straight chain of revisions keeps the rollback simple.

### Rule 5: Make sure that the previous version operates with the new schema

A schema change must not cause errors in the code of the previous version. Then, if a problem
occurs, you can return only the code (Path A). The database does not change. Divide a destructive
change into two versions: first expand the schema, then contract it.

| Change | Risk | Procedure |
| :--- | :--- | :--- |
| Add a table, a nullable column, or an index | Low | Do it in one step. |
| Add a NOT NULL column | Medium | Add the column with a `server_default`. Alternative: add the column as nullable and put values in it. Then set `nullable=False` in the next version. |
| Delete a column or a table | High in one step | Version N: stop the use of the column in the code. Version N+1: delete the column with a migration. |
| Rename a column | High in one step | Autogenerate writes a rename as "delete + add". This causes data loss. Add a new column and copy the data into it. Change the code to use the new column. Delete the old column in the next version. |
| Change a type | Medium | A larger type is safe, for example `String(64)` to `String(255)`. For a smaller or a different type, add a new column. |
| Add a UNIQUE, CHECK, or FK constraint | Medium | If some rows are incorrect for the new constraint, the migration stops with an error. Examine the data and correct it first. |

### Rule 6: Read each line that autogenerate writes

Autogenerate writes only a draft. It does not find these changes correctly:

- A rename. It writes "delete + add".
- A change to a `server_default`.
- A change to enum values.
- Some CHECK constraints.

If `upgrade()` is empty, it is possible that the model is not in `storage/models.py`.

### Rule 7: Give each constraint a name

The `naming_convention` in `storage/db.py` sets these constraint names:

- `pk_<table>`
- `uq_<table>_<column>`
- `fk_<table>_<column>_<referred_table>`
- `ix_<table>_<column>`
- `ck_<table>_<name>`

When you write a migration manually, use the same names. For an example, see
`0001_create_documents.py`. A downgrade cannot delete a constraint that has no name.

### Rule 8: Do not use native Postgres ENUM types

`sa.Enum(...)` creates a separate `TYPE` in Postgres. `op.drop_table` does not delete this type.
Because of this, an upgrade after a downgrade stops with the error `type "..." already exists`. We
tested this.

Use this code:

```python
sa.Enum(
    "equity", "bond", "fund", "etf", "cash", "other",
    name="asset_type", native_enum=False, create_constraint=True, length=32,
)
```

This code makes a `VARCHAR(32)` column and a CHECK constraint (`ck_holdings_asset_type`).

- Always set `length`. If you do not set it, the column length is the length of the longest value
  (6 in this example). Then the column is too short for a longer value in the future.
- Use this code for `asset_type`, `status`, `weight_basis`, and all similar fields.
- To add a new value, write a migration that deletes the CHECK constraint and creates it again.
  Use a batch operation for this change (Rule 10).

### Rule 9: Data migrations

- Do not import `storage.models` in a migration. The model changes over time. Then the old
  migration does not operate. Define the columns that you use in the migration:

  ```python
  holdings = sa.table("holdings", sa.column("status", sa.String))
  op.execute(holdings.update().where(holdings.c.status.is_(None)).values(status="ok"))
  ```

- Put schema changes and data changes in different migrations.
- Write a `downgrade()` for a data migration too. If the downgrade cannot restore the data, write a
  `DATA LOSS:` line (Rule 2).

### Rule 10: Use `batch_alter_table` for changes to tables

The tests also use SQLite. SQLite cannot do `ALTER COLUMN`. The error is `near "TYPE": syntax error`. Put each column change,
each column delete, and each constraint change in a batch operation:

```python
with op.batch_alter_table("documents") as batch:
    batch.alter_column("storage_key", type_=sa.String(512))
```

- `migrations/env.py` sets `render_as_batch=True`. Because of this, autogenerate writes batch
  operations automatically. On Postgres, a batch operation is a usual `ALTER TABLE`.
- If you must use a type that only Postgres has (for example, JSONB), give an SQLite alternative:
  `sa.JSON().with_variant(postgresql.JSONB(), "postgresql")`.

## Checks before a PR

Do these checks before you open a PR that has a migration:

```bash
docker compose up -d postgres                                # in the repository root
cd backend
uv run alembic heads                                         # must show one line
uv run alembic upgrade head
uv run alembic downgrade -1 && uv run alembic upgrade head   # round trip on real Postgres
uv run pytest tests/test_migrations.py
```

Add a **Rollback** note to the PR description. Give answers to these questions:

- Does the downgrade delete data?
- Does the previous version operate with the new schema? Is Path A possible?

## Rollback procedure

Example: `v0.2.0` has a problem. You must return to `v0.1.0`. Run all commands in the repository
root.

### Step 0: Make a backup

Do this step first, each time:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > backup-$(date +%Y%m%d-%H%M).dump
```

Also make a backup with this command **before** each deploy that has a migration. Path C uses that
backup.

### Step 1: Compare the revisions

```bash
docker run --rm ghcr.io/wauf/fund_research_platform/api:v0.1.0 alembic heads   # head of the old version (no database necessary)
APP_VERSION=v0.2.0 docker compose run --rm migrate alembic current             # current revision of the database
```

- If the two revisions are the same, the schema did not change between the versions. Run
  `APP_VERSION=v0.1.0 docker compose up -d`. Then go to Step 3.
- If the two revisions are different, select Path A, Path B, or Path C.

### Step 2, Path A: Return only the code

Use this path only if the schema change is an "expand" change (Rule 5).

```bash
APP_VERSION=v0.1.0 docker compose up -d --no-deps api web
```

- The database remains on the new schema. No data loss occurs.
- The `--no-deps` option is necessary. Without it, the old `migrate` service starts and stops with
  an error.
- Path A is a temporary condition. The next full `docker compose up -d` with the old image also
  stops with an error. Because of this, correct the problem in a new version and deploy that
  version.

### Step 2, Path B: Return the database and the code

```bash
APP_VERSION=v0.2.0 docker compose run --rm migrate alembic downgrade 0001   # 0001 = old head from Step 1. Use the NEW image.
APP_VERSION=v0.1.0 docker compose up -d
```

- Do the two commands in this sequence. Only the new image has the downgrade code.
- This path deletes the data that `DATA LOSS:` migrations added. The backup from Step 0 keeps
  this data.

### Step 2, Path C: Restore from a backup

Use this path if there is no downgrade. Also use it if the downgrade stopped with an error. You
must have a backup from **before** the deploy.

CAUTION: Make sure that the team accepts this data loss. Path C deletes all data that the system
wrote after the backup.

CAUTION: Delete the database and create it again before the restore. `pg_restore --clean` deletes
only the objects that are in the backup. The tables from the new version remain and cause errors
in the next upgrade.

```bash
docker compose stop api web
docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' < backup-before-v0.2.0.dump
APP_VERSION=v0.1.0 docker compose up -d
```

### Step 3: Do a check of the result

```bash
APP_VERSION=v0.1.0 docker compose run --rm migrate alembic current   # must show the old head
curl -fsS http://localhost:8000/health
```

## Manual rollback test

Make two versions on your computer. Then do the full rollback procedure. For the new version, a
test branch is enough. For example, the test branch can add a nullable column to the `documents`
table.

```bash
git switch main
APP_VERSION=v0.1.0 docker compose up -d --build --wait   # old version: upload a PDF
git switch <branch-with-migration>
APP_VERSION=v0.2.0 docker compose up -d --build --wait   # new version: the migration runs. Add data.
# Do the rollback procedure (Steps 0-3) with Path B. Then go forward again and do Path A.
APP_VERSION=v0.2.0 docker compose up -d --wait           # forward again: the upgrade must run again
```

After each step, do a check of these items:

- The output of `alembic current`
- The `/health` endpoint
- The record of the PDF that you uploaded
