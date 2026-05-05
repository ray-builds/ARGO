"""Initial schema — all tables

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# All PKs and FKs are VARCHAR(36) UUIDs generated server-side (str(uuid.uuid4())).
# Using String/VARCHAR instead of the native UUID type keeps the schema
# compatible with SQLite (dev/CI) and PostgreSQL (production) without
# dialect-specific columns.


def upgrade() -> None:
    # ── 1. users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("azure_oid", sa.String(128), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(64), nullable=False, server_default="staff"),
        sa.Column("whatsapp_number", sa.String(32), nullable=True),
        sa.Column("preferences", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        # graph token columns added in migration 0002; declared here as NOT present
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("azure_oid", name="uq_users_azure_oid"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("idx_users_azure_oid", "users", ["azure_oid"])
    op.create_index("idx_users_email", "users", ["email"])

    # ── 2. emails ─────────────────────────────────────────────────────────────
    op.create_table(
        "emails",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("graph_message_id", sa.String(512), nullable=False),
        sa.Column("mailbox_user_email", sa.String(255), nullable=False),
        sa.Column("sender_email", sa.String(255), nullable=False),
        sa.Column("sender_name", sa.String(255), nullable=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_preview", sa.Text(), nullable=True),
        sa.Column("body_full", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("relevance_score", sa.SmallInteger(), nullable=True),
        sa.Column("tag", sa.String(32), nullable=True),
        sa.Column("is_from_ceo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_email", sa.String(255), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_message_id", name="uq_emails_graph_message_id"),
    )
    op.create_index("idx_emails_mailbox", "emails", ["mailbox_user_email"])
    op.create_index("idx_emails_received_at", "emails", ["received_at"])
    op.create_index("idx_emails_sender", "emails", ["sender_email"])
    op.create_index("idx_emails_tag", "emails", ["tag"])
    op.create_index("idx_emails_from_ceo", "emails", ["is_from_ceo"])
    op.create_index("idx_emails_received_score", "emails", ["received_at", "relevance_score"])
    op.create_index("idx_emails_mailbox_received", "emails", ["mailbox_user_email", "received_at"])
    op.create_index("idx_emails_mailbox_tag", "emails", ["mailbox_user_email", "tag"])
    op.create_index("idx_emails_ceo_received", "emails", ["is_from_ceo", "received_at"])

    # ── 3. email_highlights ───────────────────────────────────────────────────
    op.create_table(
        "email_highlights",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("email_id", sa.String(36), nullable=False),
        sa.Column("highlight_text", sa.Text(), nullable=False),
        sa.Column("action_required", sa.Text(), nullable=True),
        sa.Column("key_conclusion", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_email_highlights_email_id", "email_highlights", ["email_id"])

    # ── 4. overnight_summaries ────────────────────────────────────────────────
    op.create_table(
        "overnight_summaries",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("coverage_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coverage_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("email_section", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("market_moves_section", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("news_section", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("macro_section", sa.Text(), nullable=True),
        sa.Column("full_briefing_text", sa.Text(), nullable=False),
        sa.Column("whatsapp_delivered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("whatsapp_delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("whatsapp_error", sa.Text(), nullable=True),
        sa.Column("email_delivered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("email_delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_error", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(64), nullable=False),
        sa.Column("raw_inputs", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("summary_date", name="uq_overnight_summaries_date"),
    )
    op.create_index("idx_overnight_summaries_date", "overnight_summaries", ["summary_date"])

    # ── 5. meetings ───────────────────────────────────────────────────────────
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("meeting_type", sa.String(32), nullable=False),
        sa.Column("meeting_date", sa.Date(), nullable=False),
        sa.Column("attendees", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("uploaded_by_email", sa.String(255), nullable=False),
        sa.Column("audio_file_path", sa.String(1024), nullable=True),
        sa.Column("transcript_raw", sa.Text(), nullable=True),
        sa.Column("transcript_clean", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("decisions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("key_quotes", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("transcription_model", sa.String(64), nullable=True),
        sa.Column("summary_model", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_meetings_date", "meetings", ["meeting_date"])
    op.create_index("idx_meetings_type", "meetings", ["meeting_type"])
    op.create_index("idx_meetings_status", "meetings", ["status"])
    op.create_index("idx_meetings_date_type", "meetings", ["meeting_date", "meeting_type"])

    # ── 6. meeting_action_items ───────────────────────────────────────────────
    op.create_table(
        "meeting_action_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("meeting_id", sa.String(36), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_meeting_action_items_meeting_id", "meeting_action_items", ["meeting_id"])

    # ── 7. documents ──────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=True),
        sa.Column("original_filename", sa.String(512), nullable=True),
        sa.Column("file_path", sa.String(1024), nullable=True),
        sa.Column("content_raw", sa.Text(), nullable=True),
        sa.Column("asset_class", sa.String(32), nullable=True),
        sa.Column("tag", sa.String(64), nullable=True),
        sa.Column("uploaded_by_email", sa.String(255), nullable=False),
        sa.Column("quality_rating", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_documents_source_type", "documents", ["source_type"])
    op.create_index("idx_documents_asset_class", "documents", ["asset_class"])
    op.create_index("idx_documents_tag", "documents", ["tag"])

    # ── 8. document_chunks ────────────────────────────────────────────────────
    # TODO: embedding column (Vector(1536)) is deliberately omitted here for
    # SQLite / pgvector-free compatibility. Add it in a separate migration for
    # PostgreSQL+pgvector production environments using:
    #   op.add_column("document_chunks", sa.Column("embedding", Vector(1536), nullable=True))
    # after running `CREATE EXTENSION IF NOT EXISTS vector;` on the database.
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index(
        "idx_document_chunks_doc_index", "document_chunks", ["document_id", "chunk_index"]
    )

    # ── 9. positions ──────────────────────────────────────────────────────────
    op.create_table(
        "positions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("portfolio_name", sa.String(128), nullable=False, server_default="main"),
        sa.Column("instrument", sa.String(255), nullable=False),
        sa.Column("instrument_type", sa.String(32), nullable=False),
        sa.Column("asset_class", sa.String(32), nullable=False),
        sa.Column("geography", sa.String(64), nullable=True),
        sa.Column("notional", sa.Numeric(20, 4), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("current_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("pnl", sa.Numeric(20, 4), nullable=True),
        sa.Column("weight_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("uploaded_by_email", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_positions_portfolio", "positions", ["portfolio_name"])
    op.create_index("idx_positions_instrument_type", "positions", ["instrument_type"])
    op.create_index("idx_positions_asset_class", "positions", ["asset_class"])
    op.create_index("idx_positions_date", "positions", ["as_of_date"])
    op.create_index("idx_positions_portfolio_date", "positions", ["portfolio_name", "as_of_date"])

    # ── 10. scenarios ─────────────────────────────────────────────────────────
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("scenario_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("macro_view_input", sa.Text(), nullable=True),
        sa.Column("analysis_output", sa.Text(), nullable=False),
        sa.Column("trade_ideas", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("model_used", sa.String(64), nullable=False),
        sa.Column("created_by_email", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_scenarios_type", "scenarios", ["scenario_type"])

    # ── 11. clients ───────────────────────────────────────────────────────────
    op.create_table(
        "clients",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("firm", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("tier", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("last_contact_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_email", sa.String(255), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_clients_email", "clients", ["email"])
    op.create_index("idx_clients_tier", "clients", ["tier"])
    op.create_index("idx_clients_last_contact_date", "clients", ["last_contact_date"])
    op.create_index("idx_clients_is_active", "clients", ["is_active"])
    op.create_index("idx_clients_tier_contact", "clients", ["tier", "last_contact_date"])

    # ── 12. client_interactions ───────────────────────────────────────────────
    op.create_table(
        "client_interactions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column("interaction_type", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False, server_default="outbound"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("logged_by_email", sa.String(255), nullable=False),
        sa.Column("interaction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_client_interactions_client_id", "client_interactions", ["client_id"])
    op.create_index("idx_client_interactions_type", "client_interactions", ["interaction_type"])
    op.create_index("idx_client_interactions_date", "client_interactions", ["interaction_date"])

    # ── 13. research_items ────────────────────────────────────────────────────
    op.create_table(
        "research_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("supplier_name", sa.String(255), nullable=True),   # optional — not all have a supplier
        sa.Column("supplier_email", sa.String(255), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("asset_class", sa.String(32), nullable=True),
        sa.Column("thesis_summary", sa.Text(), nullable=True),
        sa.Column("key_data_points", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("conviction_level", sa.String(16), nullable=True),
        sa.Column("quality_rating", sa.SmallInteger(), nullable=True),
        sa.Column("document_id", sa.String(36), nullable=True),
        sa.Column("published_date", sa.Date(), nullable=True),
        sa.Column("ingested_by_email", sa.String(255), nullable=False),
        sa.Column("topics", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("model_used", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        # Soft FK: document_id references documents.id but is not enforced as a hard
        # constraint because a ResearchItem may exist without an associated Document.
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            ondelete="SET NULL",
            name="fk_research_items_document_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_research_items_source_type", "research_items", ["source_type"])
    op.create_index("idx_research_items_asset_class", "research_items", ["asset_class"])
    op.create_index("idx_research_items_conviction", "research_items", ["conviction_level"])
    op.create_index("idx_research_items_document_id", "research_items", ["document_id"])
    op.create_index(
        "idx_research_items_asset_conviction",
        "research_items", ["asset_class", "conviction_level"],
    )

    # ── 14. economic_events ───────────────────────────────────────────────────
    op.create_table(
        "economic_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("event_name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=False),
        sa.Column("release_time_utc", sa.Time(timezone=False), nullable=True),
        sa.Column("importance", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("forecast", sa.String(64), nullable=True),
        sa.Column("actual", sa.String(64), nullable=True),
        sa.Column("previous", sa.String(64), nullable=True),
        sa.Column("surprise_direction", sa.String(16), nullable=True),
        sa.Column("ai_analysis", sa.Text(), nullable=True),
        sa.Column("alert_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("data_source", sa.String(32), nullable=False, server_default="MANUAL"),
        sa.Column("external_event_id", sa.String(255), nullable=True),
        sa.Column("model_used", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_economic_events_country", "economic_events", ["country"])
    op.create_index("idx_economic_events_release_date", "economic_events", ["release_date"])
    op.create_index("idx_economic_events_importance", "economic_events", ["importance"])
    op.create_index("idx_economic_events_external_id", "economic_events", ["external_event_id"])
    op.create_index(
        "idx_economic_events_date_importance",
        "economic_events", ["release_date", "importance"],
    )

    # ── 15. chat_conversations ────────────────────────────────────────────────
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("user_email", sa.String(255), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("module_context", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            ondelete="SET NULL",
            name="fk_chat_conversations_user_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chat_conversations_user_id", "chat_conversations", ["user_id"])
    op.create_index("idx_chat_conversations_user_email", "chat_conversations", ["user_email"])
    op.create_index("idx_chat_conversations_context", "chat_conversations", ["module_context"])
    op.create_index("idx_chat_conversations_is_active", "chat_conversations", ["is_active"])

    # ── 16. chat_messages ─────────────────────────────────────────────────────
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.Text(), nullable=True),
        sa.Column("tool_results", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(64), nullable=True),
        sa.Column("token_input", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_output", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sequence_num", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["chat_conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chat_messages_conversation_id", "chat_messages", ["conversation_id"])
    op.create_index(
        "idx_chat_messages_conv_seq", "chat_messages", ["conversation_id", "sequence_num"]
    )


def downgrade() -> None:
    # Drop tables in reverse FK-dependency order; indexes are dropped automatically.
    op.drop_table("chat_messages")
    op.drop_table("chat_conversations")
    op.drop_table("economic_events")
    op.drop_table("research_items")
    op.drop_table("client_interactions")
    op.drop_table("clients")
    op.drop_table("scenarios")
    op.drop_table("positions")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("meeting_action_items")
    op.drop_table("meetings")
    op.drop_table("overnight_summaries")
    op.drop_table("email_highlights")
    op.drop_table("emails")
    op.drop_table("users")
