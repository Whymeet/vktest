"""Add scheduled_enabled column to scaling_configs

Revision ID: add_scheduled_enabled
Revises: add_banner_level_scaling
Create Date: 2025-12-30
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_scheduled_enabled'
down_revision = 'add_banner_level_scaling'
branch_labels = None
depends_on = None


def upgrade():
    # Add scheduled_enabled field to scaling_configs
    # TRUE = run by schedule, FALSE = manual only
    op.add_column('scaling_configs', sa.Column('scheduled_enabled', sa.Boolean(), nullable=True, server_default='1'))


def downgrade():
    op.drop_column('scaling_configs', 'scheduled_enabled')
