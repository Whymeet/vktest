"""Add scaling_config_accounts table

Revision ID: add_scaling_accounts
Revises: add_scaling_tables
Create Date: 2024-12-09
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_scaling_accounts'
down_revision = 'add_scaling_tables'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scaling_config_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['config_id'], ['scaling_configs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scaling_config_accounts_id'), 'scaling_config_accounts', ['id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_scaling_config_accounts_id'), table_name='scaling_config_accounts')
    op.drop_table('scaling_config_accounts')
