from alembic import op
import sqlalchemy as sa

revision = "001_add_booking_idempotency"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "consultations",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_consultations_idempotency_key",
        "consultations",
        ["idempotency_key"],
        unique=True,
    )

def downgrade():
    op.drop_index(
        "ix_consultations_idempotency_key",
        table_name="consultations",
    )
    op.drop_column("consultations", "idempotency_key")
