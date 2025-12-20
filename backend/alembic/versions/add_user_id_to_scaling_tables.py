"""Add user_id to scaling tables

Revision ID: add_user_id_scaling
Revises: add_duplicates_count
Create Date: 2025-12-20
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_user_id_scaling'
down_revision = 'add_composite_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add user_id to scaling_configs
    # First add as nullable, then update existing rows, then make NOT NULL
    op.add_column('scaling_configs', sa.Column('user_id', sa.Integer(), nullable=True))

    # Update existing rows to have user_id = 1 (default user)
    # This is safe because we need some value for existing configs
    op.execute("UPDATE scaling_configs SET user_id = 1 WHERE user_id IS NULL")

    # Now make it NOT NULL
    op.alter_column('scaling_configs', 'user_id', nullable=False)

    # Add foreign key and index
    op.create_foreign_key(
        'fk_scaling_configs_user_id',
        'scaling_configs', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_scaling_configs_user_id', 'scaling_configs', ['user_id'])

    # Add user_id to scaling_logs
    op.add_column('scaling_logs', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("UPDATE scaling_logs SET user_id = 1 WHERE user_id IS NULL")
    op.alter_column('scaling_logs', 'user_id', nullable=False)
    op.create_foreign_key(
        'fk_scaling_logs_user_id',
        'scaling_logs', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_scaling_logs_user_id', 'scaling_logs', ['user_id'])

    # Add user_id to scaling_config_accounts
    op.add_column('scaling_config_accounts', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("UPDATE scaling_config_accounts SET user_id = 1 WHERE user_id IS NULL")
    op.alter_column('scaling_config_accounts', 'user_id', nullable=False)
    op.create_foreign_key(
        'fk_scaling_config_accounts_user_id',
        'scaling_config_accounts', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_scaling_config_accounts_user_id', 'scaling_config_accounts', ['user_id'])


def downgrade() -> None:
    # Remove from scaling_config_accounts
    op.drop_index('ix_scaling_config_accounts_user_id', table_name='scaling_config_accounts')
    op.drop_constraint('fk_scaling_config_accounts_user_id', 'scaling_config_accounts', type_='foreignkey')
    op.drop_column('scaling_config_accounts', 'user_id')

    # Remove from scaling_logs
    op.drop_index('ix_scaling_logs_user_id', table_name='scaling_logs')
    op.drop_constraint('fk_scaling_logs_user_id', 'scaling_logs', type_='foreignkey')
    op.drop_column('scaling_logs', 'user_id')

    # Remove from scaling_configs
    op.drop_index('ix_scaling_configs_user_id', table_name='scaling_configs')
    op.drop_constraint('fk_scaling_configs_user_id', 'scaling_configs', type_='foreignkey')
    op.drop_column('scaling_configs', 'user_id')
