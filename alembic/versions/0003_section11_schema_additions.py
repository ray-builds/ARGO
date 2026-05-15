"""Section 11 schema additions.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-15 12:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(name)


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(i.get("name") == index_name for i in indexes)


def upgrade() -> None:
    # WhatsApp messages
    if not _table_exists("whatsapp_messages"):
        op.create_table(
            "whatsapp_messages",
            sa.Column("id", sa.String(128), nullable=False),
            sa.Column("group_name", sa.String(255), nullable=True),
            sa.Column("author", sa.String(255), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("is_trade_related", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("classification", sa.Text(), nullable=True),
            sa.Column("compliance_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id"),
        )
    if _table_exists("whatsapp_messages"):
        if not _index_exists("whatsapp_messages", "idx_wa_timestamp"):
            op.create_index("idx_wa_timestamp", "whatsapp_messages", ["timestamp"])
        if not _index_exists("whatsapp_messages", "idx_wa_trade"):
            op.create_index("idx_wa_trade", "whatsapp_messages", ["is_trade_related"])

    # Meeting summaries
    if not _table_exists("meeting_summaries"):
        op.create_table(
            "meeting_summaries",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("meeting_title", sa.String(512), nullable=False),
            sa.Column("meeting_date", sa.Date(), nullable=False),
            sa.Column("participants", sa.Text(), nullable=True),
            sa.Column("transcript_onedrive_path", sa.String(1024), nullable=True),
            sa.Column("summary_json", sa.Text(), nullable=False),
            sa.Column("transcription_method", sa.String(32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id"),
        )

    # Research documents
    if not _table_exists("research_documents"):
        op.create_table(
            "research_documents",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("source_firm", sa.String(255), nullable=False),
            sa.Column("title", sa.String(512), nullable=False),
            sa.Column("source_url", sa.String(2048), nullable=True),
            sa.Column("doc_type", sa.String(64), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("content_text", sa.Text(), nullable=True),
            # pgvector vector(1536) is represented as Text for sqlite/dev portability.
            sa.Column("embedding_vector", sa.Text(), nullable=True),
            sa.Column("analysis_json", sa.Text(), nullable=True),
            sa.Column("onedrive_path", sa.String(1024), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_url", name="uq_research_documents_source_url"),
        )
    if _table_exists("research_documents") and not _index_exists("research_documents", "idx_research_date"):
        op.create_index("idx_research_date", "research_documents", ["date"])

    # Portfolio-research conflicts
    if not _table_exists("portfolio_research_conflicts"):
        op.create_table(
            "portfolio_research_conflicts",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("research_id", sa.String(36), nullable=True),
            sa.Column("position_instrument", sa.String(255), nullable=False),
            sa.Column("conflict_type", sa.String(64), nullable=False),
            sa.Column("severity", sa.String(16), nullable=False),
            sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["research_id"], ["research_documents.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    # Economic releases
    if not _table_exists("economic_releases"):
        op.create_table(
            "economic_releases",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("indicator_name", sa.String(255), nullable=False),
            sa.Column("release_datetime", sa.DateTime(timezone=True), nullable=False),
            sa.Column("actual_value", sa.Numeric(20, 6), nullable=True),
            sa.Column("consensus_value", sa.Numeric(20, 6), nullable=True),
            sa.Column("prior_value", sa.Numeric(20, 6), nullable=True),
            sa.Column("surprise_direction", sa.String(32), nullable=True),
            sa.Column("ai_commentary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id"),
        )

    # Graph subscriptions: create if missing using a superset schema that supports current code.
    if not _table_exists("graph_subscriptions"):
        op.create_table(
            "graph_subscriptions",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("subscription_id", sa.String(128), nullable=False),
            sa.Column("user_email", sa.String(255), nullable=True),
            sa.Column("resource", sa.Text(), nullable=False),
            sa.Column("change_types", sa.String(128), nullable=True),
            sa.Column("client_state", sa.String(128), nullable=False),
            sa.Column("notification_url", sa.Text(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expiration_datetime", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_renewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("subscription_id", name="uq_graph_subscriptions_subscription_id"),
        )


def downgrade() -> None:
    if _table_exists("economic_releases"):
        op.drop_table("economic_releases")
    if _table_exists("portfolio_research_conflicts"):
        op.drop_table("portfolio_research_conflicts")
    if _table_exists("research_documents"):
        if _index_exists("research_documents", "idx_research_date"):
            op.drop_index("idx_research_date", table_name="research_documents")
        op.drop_table("research_documents")
    if _table_exists("meeting_summaries"):
        op.drop_table("meeting_summaries")
    if _table_exists("whatsapp_messages"):
        if _index_exists("whatsapp_messages", "idx_wa_trade"):
            op.drop_index("idx_wa_trade", table_name="whatsapp_messages")
        if _index_exists("whatsapp_messages", "idx_wa_timestamp"):
            op.drop_index("idx_wa_timestamp", table_name="whatsapp_messages")
        op.drop_table("whatsapp_messages")
