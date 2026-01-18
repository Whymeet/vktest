"""Add new_banner_name_template to scaling_configs

Revision ID: add_banner_name_template
Revises: add_roi_sub_field
Create Date: 2026-01-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_banner_name_template'
down_revision = 'add_roi_sub_field'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new_banner_name_template column to scaling_configs
    # This field stores a template for banner names with {date} placeholder support
    op.add_column('scaling_configs', sa.Column('new_banner_name_template', sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column('scaling_configs', 'new_banner_name_template')
