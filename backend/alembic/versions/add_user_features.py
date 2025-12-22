"""Add user_features table for feature access control

Revision ID: add_user_features
Revises: add_composite_indexes
Create Date: 2025-12-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_user_features'
down_revision = 'add_composite_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_features table
    op.create_table(
        'user_features',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('feature', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'feature', name='uix_user_feature')
    )
    op.create_index(op.f('ix_user_features_id'), 'user_features', ['id'], unique=False)
    op.create_index(op.f('ix_user_features_user_id'), 'user_features', ['user_id'], unique=False)

    # Give all existing users full access to all features
    # This maintains backwards compatibility
    connection = op.get_bind()

    # Get all existing user IDs
    users_result = connection.execute(sa.text("SELECT id FROM users"))
    user_ids = [row[0] for row in users_result]

    # Available features
    features = ['auto_disable', 'scaling', 'leadstech', 'logs']

    # Insert features for each user
    for user_id in user_ids:
        for feature in features:
            connection.execute(
                sa.text(
                    "INSERT INTO user_features (user_id, feature, created_at) VALUES (:user_id, :feature, NOW())"
                ),
                {"user_id": user_id, "feature": feature}
            )


def downgrade() -> None:
    op.drop_index(op.f('ix_user_features_user_id'), table_name='user_features')
    op.drop_index(op.f('ix_user_features_id'), table_name='user_features')
    op.drop_table('user_features')
