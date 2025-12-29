"""Add banner-level scaling fields to ScalingConfig and ScalingLog

Revision ID: add_banner_level_scaling
Revises: add_user_features
Create Date: 2025-12-28
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_banner_level_scaling'
down_revision = 'add_user_features'
branch_labels = None
depends_on = None


def upgrade():
    # Add banner-level scaling fields to scaling_configs
    op.add_column('scaling_configs', sa.Column('activate_positive_banners', sa.Boolean(), nullable=True, server_default='1'))
    op.add_column('scaling_configs', sa.Column('duplicate_negative_banners', sa.Boolean(), nullable=True, server_default='1'))
    op.add_column('scaling_configs', sa.Column('activate_negative_banners', sa.Boolean(), nullable=True, server_default='0'))

    # Add banner classification fields to scaling_logs
    op.add_column('scaling_logs', sa.Column('positive_banner_ids', sa.JSON(), nullable=True))
    op.add_column('scaling_logs', sa.Column('negative_banner_ids', sa.JSON(), nullable=True))
    op.add_column('scaling_logs', sa.Column('positive_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('scaling_logs', sa.Column('negative_count', sa.Integer(), nullable=True, server_default='0'))


def downgrade():
    # Remove from scaling_logs
    op.drop_column('scaling_logs', 'negative_count')
    op.drop_column('scaling_logs', 'positive_count')
    op.drop_column('scaling_logs', 'negative_banner_ids')
    op.drop_column('scaling_logs', 'positive_banner_ids')

    # Remove from scaling_configs
    op.drop_column('scaling_configs', 'activate_negative_banners')
    op.drop_column('scaling_configs', 'duplicate_negative_banners')
    op.drop_column('scaling_configs', 'activate_positive_banners')
