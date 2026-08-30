"""Paso 3: tabla de trazas vectorizadas para la ingesta híbrida de logs."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision = "0002_traces"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("embedding", VECTOR(64), nullable=False),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("source_quality", sa.String(30), nullable=False),
        sa.Column("services", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("levels", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("user_id", sa.Integer()),
        sa.Column("payment_id", sa.String(64)),
        sa.Column("status_code", sa.Integer()),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_path", "trace_id"),
    )
    op.create_index("ix_traces_trace_id", "traces", ["trace_id"])
    op.execute("CREATE INDEX ix_traces_embedding_hnsw ON traces USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.drop_index("ix_traces_embedding_hnsw", table_name="traces")
    op.drop_index("ix_traces_trace_id", table_name="traces")
    op.drop_table("traces")
