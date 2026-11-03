"""create extraction_runs, holdings, report_summaries

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-03

Expand-only change: three new tables, nothing in documents changes, so the previous version runs
on this schema unchanged (rollback Path A is possible).

DATA LOSS: downgrade() drops the three tables with every extraction run, holding and report
summary in them. Uploaded documents are kept. Take a backup first (db-migrations skill, step 0).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Enum values as of this revision. Not imported from schemas.holding: that module changes over
# time, this migration must not (db-migrations skill, rule 9).
STATUS = ("ok", "needs_review")
REPORT_KIND = ("monthly", "weekly")
ASSET_TYPE = (
    "equity",
    "bond",
    "fund",
    "etf",
    "deposit",
    "repo",
    "derivative",
    "cash",
    "other",
)
WEIGHT_BASIS = ("portfolio", "total", "unknown")

BIG_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
AMOUNT = sa.Numeric(24, 6)
WEIGHT = sa.Numeric(16, 10)


def str_enum(values: tuple[str, ...], name: str, length: int) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=length)


def report_scoped_columns() -> list[sa.Column]:
    """Columns of schemas.holding._ReportScoped (fresh objects for each table)."""
    return [
        sa.Column("fund_code", sa.String(6), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("report_kind", str_enum(REPORT_KIND, "report_kind", 16), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("status", str_enum(STATUS, "status", 16), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("status", str_enum(STATUS, "status", 16), nullable=False),
        sa.Column("issues", JSON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_extraction_runs_document_id_documents",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_extraction_runs"),
    )
    op.create_index("ix_extraction_runs_document_id", "extraction_runs", ["document_id"])

    op.create_table(
        "holdings",
        sa.Column("id", BIG_ID, nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("asset_type", str_enum(ASSET_TYPE, "asset_type", 32), nullable=False),
        sa.Column("isin", sa.String(12), nullable=True),
        sa.Column("instrument_code", sa.String(32), nullable=True),
        sa.Column("held_fund_code", sa.String(6), nullable=True),
        sa.Column("nominal", AMOUNT, nullable=True),
        sa.Column("value", AMOUNT, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("weight", WEIGHT, nullable=False),
        sa.Column("weight_basis", str_enum(WEIGHT_BASIS, "weight_basis", 16), nullable=False),
        *report_scoped_columns(),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"],
            ["extraction_runs.id"],
            name="fk_holdings_extraction_run_id_extraction_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_holdings"),
        sa.UniqueConstraint("extraction_run_id", "row_no", name="uq_holdings_extraction_run_id"),
    )
    op.create_index("ix_holdings_fund_code", "holdings", ["fund_code"])
    op.create_index("ix_holdings_isin", "holdings", ["isin"])

    op.create_table(
        "report_summaries",
        sa.Column("id", BIG_ID, nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_value", AMOUNT, nullable=False),
        sa.Column("cash_equivalents", AMOUNT, nullable=False),
        sa.Column("receivables", AMOUNT, nullable=False),
        sa.Column("other_assets", AMOUNT, nullable=False),
        sa.Column("liabilities", AMOUNT, nullable=False),
        sa.Column("total_value", AMOUNT, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        *report_scoped_columns(),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"],
            ["extraction_runs.id"],
            name="fk_report_summaries_extraction_run_id_extraction_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_report_summaries"),
        sa.UniqueConstraint("extraction_run_id", name="uq_report_summaries_extraction_run_id"),
    )
    op.create_index("ix_report_summaries_fund_code", "report_summaries", ["fund_code"])


def downgrade() -> None:
    # Children first: holdings and report_summaries reference extraction_runs.
    op.drop_index("ix_report_summaries_fund_code", table_name="report_summaries")
    op.drop_table("report_summaries")
    op.drop_index("ix_holdings_isin", table_name="holdings")
    op.drop_index("ix_holdings_fund_code", table_name="holdings")
    op.drop_table("holdings")
    op.drop_index("ix_extraction_runs_document_id", table_name="extraction_runs")
    op.drop_table("extraction_runs")
