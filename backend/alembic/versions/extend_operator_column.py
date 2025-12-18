"""Extend operator column size to support longer operator names

Revision ID: extend_operator_column
Revises: add_duplicated_banner_ids
Create Date: 2024-12-18 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'extend_operator_column'
down_revision = 'add_duplicated_banner_ids'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend operator column from VARCHAR(10) to VARCHAR(20) to support
    # longer operator names like 'greater_or_equal', 'less_or_equal'
    op.alter_column(
        'scaling_conditions',
        'operator',
        type_=sa.String(20),
        existing_type=sa.String(10),
        existing_nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        'scaling_conditions',
        'operator',
        type_=sa.String(10),
        existing_type=sa.String(20),
        existing_nullable=False
    )
