"""Add task_id column to scaling_logs

Revision ID: add_task_id_to_scaling_logs
Revises: add_scaling_task_errors
Create Date: 2026-01-14

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_task_id_to_scaling_logs'
down_revision = 'add_scaling_task_errors'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add task_id column to scaling_logs table
    op.add_column('scaling_logs', sa.Column('task_id', sa.Integer(), nullable=True))
    
    # Create foreign key to scaling_tasks
    op.create_foreign_key(
        'fk_scaling_logs_task_id',
        'scaling_logs',
        'scaling_tasks',
        ['task_id'],
        ['id'],
        ondelete='SET NULL'
    )
    
    # Create index for faster lookups
    op.create_index('ix_scaling_logs_task_id', 'scaling_logs', ['task_id'])


def downgrade() -> None:
    op.drop_index('ix_scaling_logs_task_id', table_name='scaling_logs')
    op.drop_constraint('fk_scaling_logs_task_id', 'scaling_logs', type_='foreignkey')
    op.drop_column('scaling_logs', 'task_id')
