"""Add composite indexes for query optimization

Revision ID: add_composite_indexes
Revises: extend_operator_column
Create Date: 2024-12-18 16:00:00.000000

This migration adds composite indexes to improve query performance:
- BannerAction: user_id + action + created_at (most common query pattern)
- BannerAction: user_id + vk_account_id (filter by account)
- BannerAction: user_id + account_name + created_at (filter by account name)
- DailyAccountStats: user_id + stats_date (date range queries)
- DailyAccountStats: user_id + account_name + stats_date
- LeadsTechAnalysisResult: user_id + cabinet_name (filter by cabinet)
- LeadsTechAnalysisResult: user_id + roi_percent (ROI sorting)
- ScalingLog: user_id + config_id (filter by config)
- ScalingLog: user_id + created_at (date sorting)
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'add_composite_indexes'
down_revision = 'extend_operator_column'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # BannerAction indexes
    op.create_index(
        'ix_banner_actions_user_action_created',
        'banner_actions',
        ['user_id', 'action', 'created_at'],
        unique=False
    )
    op.create_index(
        'ix_banner_actions_user_account',
        'banner_actions',
        ['user_id', 'vk_account_id'],
        unique=False
    )
    op.create_index(
        'ix_banner_actions_user_account_name_created',
        'banner_actions',
        ['user_id', 'account_name', 'created_at'],
        unique=False
    )

    # DailyAccountStats indexes
    op.create_index(
        'ix_daily_stats_user_date',
        'daily_account_stats',
        ['user_id', 'stats_date'],
        unique=False
    )
    op.create_index(
        'ix_daily_stats_user_account_date',
        'daily_account_stats',
        ['user_id', 'account_name', 'stats_date'],
        unique=False
    )

    # LeadsTechAnalysisResult indexes
    op.create_index(
        'ix_lt_results_user_cabinet',
        'leadstech_analysis_results',
        ['user_id', 'cabinet_name'],
        unique=False
    )
    op.create_index(
        'ix_lt_results_user_roi',
        'leadstech_analysis_results',
        ['user_id', 'roi_percent'],
        unique=False
    )

    # ScalingLog indexes
    op.create_index(
        'ix_scaling_logs_user_config',
        'scaling_logs',
        ['user_id', 'config_id'],
        unique=False
    )
    op.create_index(
        'ix_scaling_logs_user_created',
        'scaling_logs',
        ['user_id', 'created_at'],
        unique=False
    )


def downgrade() -> None:
    # ScalingLog indexes
    op.drop_index('ix_scaling_logs_user_created', table_name='scaling_logs')
    op.drop_index('ix_scaling_logs_user_config', table_name='scaling_logs')

    # LeadsTechAnalysisResult indexes
    op.drop_index('ix_lt_results_user_roi', table_name='leadstech_analysis_results')
    op.drop_index('ix_lt_results_user_cabinet', table_name='leadstech_analysis_results')

    # DailyAccountStats indexes
    op.drop_index('ix_daily_stats_user_account_date', table_name='daily_account_stats')
    op.drop_index('ix_daily_stats_user_date', table_name='daily_account_stats')

    # BannerAction indexes
    op.drop_index('ix_banner_actions_user_account_name_created', table_name='banner_actions')
    op.drop_index('ix_banner_actions_user_account', table_name='banner_actions')
    op.drop_index('ix_banner_actions_user_action_created', table_name='banner_actions')
