"""Add roi_sub_field to disable_rules for LeadsTech integration

Revision ID: add_roi_sub_field
Revises: add_scaling_task_errors
Create Date: 2026-01-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_roi_sub_field'
down_revision = 'add_scaling_task_errors'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add roi_sub_field column to disable_rules table
    # This field specifies which LeadsTech sub field to use for ROI calculation (sub4 or sub5)
    op.add_column('disable_rules', sa.Column('roi_sub_field', sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column('disable_rules', 'roi_sub_field')
