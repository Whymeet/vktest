"""Add errors column to scaling_tasks

Revision ID: add_scaling_task_errors
Revises: add_banner_level_scaling
Create Date: 2026-01-01 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_scaling_task_errors'
down_revision = 'add_banner_level_scaling'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add errors JSON column to scaling_tasks table
    op.add_column('scaling_tasks', sa.Column('errors', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('scaling_tasks', 'errors')
