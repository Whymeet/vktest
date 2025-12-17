"""Add duplicated_banner_ids to scaling_logs

Revision ID: add_duplicated_banner_ids
Revises: add_disable_rules
Create Date: 2024-12-18 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_duplicated_banner_ids'
down_revision = 'add_disable_rules'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add duplicated_banner_ids JSON column to scaling_logs table
    op.add_column('scaling_logs', sa.Column('duplicated_banner_ids', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('scaling_logs', 'duplicated_banner_ids')
