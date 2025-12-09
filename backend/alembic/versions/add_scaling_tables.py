"""Add scaling tables

Revision ID: add_scaling_tables
Revises: 
Create Date: 2025-12-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_scaling_tables'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create scaling_configs table
    op.create_table(
        'scaling_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('enabled', sa.Boolean(), default=False),
        sa.Column('schedule_time', sa.String(length=10), nullable=False, default='08:00'),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('new_budget', sa.Float(), nullable=True),
        sa.Column('auto_activate', sa.Boolean(), default=False),
        sa.Column('lookback_days', sa.Integer(), default=7),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scaling_configs_id'), 'scaling_configs', ['id'], unique=False)

    # Create scaling_conditions table
    op.create_table(
        'scaling_conditions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.Column('metric', sa.String(length=50), nullable=False),
        sa.Column('operator', sa.String(length=10), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('order', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['config_id'], ['scaling_configs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scaling_conditions_id'), 'scaling_conditions', ['id'], unique=False)

    # Create scaling_logs table
    op.create_table(
        'scaling_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=True),
        sa.Column('config_name', sa.String(length=255), nullable=True),
        sa.Column('account_name', sa.String(length=255), nullable=True),
        sa.Column('original_group_id', sa.BigInteger(), nullable=False),
        sa.Column('original_group_name', sa.String(length=500), nullable=True),
        sa.Column('new_group_id', sa.BigInteger(), nullable=True),
        sa.Column('new_group_name', sa.String(length=500), nullable=True),
        sa.Column('stats_snapshot', sa.JSON(), nullable=True),
        sa.Column('success', sa.Boolean(), default=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('total_banners', sa.Integer(), default=0),
        sa.Column('duplicated_banners', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['config_id'], ['scaling_configs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scaling_logs_id'), 'scaling_logs', ['id'], unique=False)
    op.create_index(op.f('ix_scaling_logs_created_at'), 'scaling_logs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_scaling_logs_created_at'), table_name='scaling_logs')
    op.drop_index(op.f('ix_scaling_logs_id'), table_name='scaling_logs')
    op.drop_table('scaling_logs')
    
    op.drop_index(op.f('ix_scaling_conditions_id'), table_name='scaling_conditions')
    op.drop_table('scaling_conditions')
    
    op.drop_index(op.f('ix_scaling_configs_id'), table_name='scaling_configs')
    op.drop_table('scaling_configs')
