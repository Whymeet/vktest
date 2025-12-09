"""Add duplicates_count to scaling_configs

Revision ID: add_duplicates_count
Revises: add_scaling_accounts
Create Date: 2024-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_duplicates_count'
down_revision = 'add_scaling_accounts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add duplicates_count column to scaling_configs table
    op.add_column('scaling_configs', sa.Column('duplicates_count', sa.Integer(), nullable=True, server_default='1'))


def downgrade() -> None:
    op.drop_column('scaling_configs', 'duplicates_count')
