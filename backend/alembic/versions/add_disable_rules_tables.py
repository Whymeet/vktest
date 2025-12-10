"""Add disable rules tables

Revision ID: add_disable_rules
Revises: add_duplicates_count
Create Date: 2025-12-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_disable_rules'
down_revision = 'add_duplicates_count'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create disable_rules table
    op.create_table(
        'disable_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), default=True),
        sa.Column('priority', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_disable_rules_id'), 'disable_rules', ['id'], unique=False)

    # Create disable_rule_conditions table
    op.create_table(
        'disable_rule_conditions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('metric', sa.String(length=50), nullable=False),
        sa.Column('operator', sa.String(length=20), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('order', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['rule_id'], ['disable_rules.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_disable_rule_conditions_id'), 'disable_rule_conditions', ['id'], unique=False)

    # Create disable_rule_accounts table (many-to-many)
    op.create_table(
        'disable_rule_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['rule_id'], ['disable_rules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_disable_rule_accounts_id'), 'disable_rule_accounts', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_disable_rule_accounts_id'), table_name='disable_rule_accounts')
    op.drop_table('disable_rule_accounts')
    
    op.drop_index(op.f('ix_disable_rule_conditions_id'), table_name='disable_rule_conditions')
    op.drop_table('disable_rule_conditions')
    
    op.drop_index(op.f('ix_disable_rules_id'), table_name='disable_rules')
    op.drop_table('disable_rules')
