"""change_vector_dimensions_to_768

Revision ID: 5e220caa0d1d
Revises: e4eba9cfaa6f
Create Date: 2026-04-01 00:40:36.722421

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from migrations.utils import get_schema

# revision identifiers, used by Alembic.
revision: str = '5e220caa0d1d'
down_revision: str | None = 'e4eba9cfaa6f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

schema = get_schema()

def upgrade() -> None:
    # Drop HNSW indexes (dimension-specific, must be recreated)
    op.execute(f"DROP INDEX IF EXISTS {schema}.ix_documents_embedding_hnsw")
    op.execute(f"DROP INDEX IF EXISTS {schema}.idx_documents_embedding_hnsw")
    op.execute(f"DROP INDEX IF EXISTS {schema}.ix_message_embeddings_embedding_hnsw")
    op.execute(f"DROP INDEX IF EXISTS {schema}.idx_message_embeddings_embedding_hnsw")

    # Change column types
    op.execute(
        f"ALTER TABLE {schema}.documents "
        "ALTER COLUMN embedding TYPE vector(768) "
        "USING embedding::vector(768)"
    )
    op.execute(
        f"ALTER TABLE {schema}.message_embeddings "
        "ALTER COLUMN embedding TYPE vector(768) "
        "USING embedding::vector(768)"
    )

    # Recreate HNSW indexes for 768-dim vectors
    op.execute(
        f"CREATE INDEX ix_documents_embedding_hnsw ON {schema}.documents "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        f"CREATE INDEX ix_message_embeddings_embedding_hnsw ON {schema}.message_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {schema}.ix_documents_embedding_hnsw")
    op.execute(f"DROP INDEX IF EXISTS {schema}.ix_message_embeddings_embedding_hnsw")

    op.execute(
        f"ALTER TABLE {schema}.documents "
        "ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )
    op.execute(
        f"ALTER TABLE {schema}.message_embeddings "
        "ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )

    op.execute(
        f"CREATE INDEX ix_documents_embedding_hnsw ON {schema}.documents "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        f"CREATE INDEX ix_message_embeddings_embedding_hnsw ON {schema}.message_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )
