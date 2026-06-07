"""llm radar — suggestions + source runs + provider config

Revision ID: 0006_llm_radar
Revises: 0005_trends
Create Date: 2026-06-07 22:00:00.000000

Adds:
  - llm_suggestions table (with pgvector embedding column)
  - data_source_runs table
  - 4 columns on settings: anthropic_api_key, gemini_api_key,
    preferred_llm_provider, llm_suggestions_enabled
  - Ensures the `vector` extension exists.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006_llm_radar"
down_revision: Union[str, Sequence[str], None] = "0005_trends"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Settings additions
    op.add_column(
        "settings",
        sa.Column("anthropic_api_key", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "settings",
        sa.Column("gemini_api_key", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "settings",
        sa.Column(
            "preferred_llm_provider",
            sa.String(length=20),
            nullable=False,
            server_default="anthropic",
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "llm_suggestions_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # data_source_runs
    op.create_table(
        "data_source_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("items_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_data_source_runs_source", "data_source_runs", ["source"], unique=False
    )
    op.create_index(
        "ix_data_source_runs_started",
        "data_source_runs",
        ["started_at"],
        unique=False,
    )

    # llm_suggestions
    op.execute(
        """
        CREATE TABLE llm_suggestions (
            id UUID PRIMARY KEY,
            term VARCHAR(160) NOT NULL,
            rationale TEXT,
            provider VARCHAR(20) NOT NULL,
            embedding vector(384),
            raw_response JSONB,
            recurrence_score NUMERIC(6,4) NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            promoted_keyword_id UUID REFERENCES keyword_ideas(id) ON DELETE SET NULL,
            suggested_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index(
        "ix_llm_suggestions_status", "llm_suggestions", ["status"], unique=False
    )
    op.create_index(
        "ix_llm_suggestions_suggested_at",
        "llm_suggestions",
        ["suggested_at"],
        unique=False,
    )
    # IVFFlat index for cosine similarity. lists=10 is fine for low row counts;
    # bump after data grows. operator vector_cosine_ops is the standard pick.
    op.execute(
        "CREATE INDEX ix_llm_suggestions_embedding_cosine "
        "ON llm_suggestions USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 10)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_llm_suggestions_embedding_cosine")
    op.drop_index("ix_llm_suggestions_suggested_at", table_name="llm_suggestions")
    op.drop_index("ix_llm_suggestions_status", table_name="llm_suggestions")
    op.drop_table("llm_suggestions")
    op.drop_index("ix_data_source_runs_started", table_name="data_source_runs")
    op.drop_index("ix_data_source_runs_source", table_name="data_source_runs")
    op.drop_table("data_source_runs")
    op.drop_column("settings", "llm_suggestions_enabled")
    op.drop_column("settings", "preferred_llm_provider")
    op.drop_column("settings", "gemini_api_key")
    op.drop_column("settings", "anthropic_api_key")
