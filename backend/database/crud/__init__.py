"""
CRUD operations - modular structure
Re-exports all functions for backward compatibility
"""

# Users: User Management, Features, Tokens, Settings
from database.crud.users import (
    # User Management
    get_user_by_id,
    get_user_by_email,
    get_user_by_username,
    create_user,
    update_user,
    update_user_password,
    update_user_last_login,
    delete_user,
    get_all_users,
    # User Features
    AVAILABLE_FEATURES,
    get_user_features,
    user_has_feature,
    add_user_feature,
    remove_user_feature,
    set_user_features,
    add_all_features_to_user,
    # Refresh Tokens
    create_refresh_token,
    get_refresh_token_by_jti,
    get_refresh_token_by_hash,
    get_user_active_tokens,
    update_token_last_used,
    revoke_refresh_token,
    revoke_all_user_tokens,
    delete_expired_tokens,
    delete_revoked_tokens,
    # User Settings
    get_user_setting,
    set_user_setting,
    get_all_user_settings,
    delete_user_setting,
)

# Accounts
from database.crud.accounts import (
    get_accounts,
    get_account_by_id,
    get_account_by_db_id,
    get_account_by_name,
    create_account,
    update_account,
    update_account_label,
    update_account_leadstech,
    delete_account,
)

# Global Settings
from database.crud.settings import (
    get_setting,
    set_setting,
    get_all_settings,
    delete_setting,
)

# Whitelist
from database.crud.whitelist import (
    get_whitelist,
    add_to_whitelist,
    remove_from_whitelist,
    is_whitelisted,
    replace_whitelist,
    bulk_add_to_whitelist,
    bulk_remove_from_whitelist,
)

# Banners
from database.crud.banners import (
    # Banner Actions
    create_banner_action,
    log_disabled_banner,
    get_banner_history,
    get_disabled_banners,
    get_disabled_banners_account_names,
    # Active Banners
    get_active_banners,
    add_active_banner,
    remove_active_banner,
    update_active_banner_stats,
)

# Stats
from database.crud.stats import (
    # Process State
    get_process_state,
    get_all_process_states,
    set_process_running,
    set_process_stopped,
    update_process_status,
    clear_all_process_states,
    # Daily Account Stats
    save_account_stats,
    get_account_stats,
    get_today_stats,
    get_stats_by_date_range,
    get_account_stats_summary,
)

# LeadsTech
from database.crud.leadstech import (
    # Config
    get_leadstech_config,
    create_or_update_leadstech_config,
    delete_leadstech_config,
    # Cabinets
    get_leadstech_cabinets,
    get_leadstech_cabinet_by_account,
    create_leadstech_cabinet,
    update_leadstech_cabinet,
    delete_leadstech_cabinet,
    # Analysis Results
    save_leadstech_analysis_result,
    replace_leadstech_analysis_results,
    get_leadstech_analysis_results,
    get_leadstech_analysis_cabinet_names,
    get_leadstech_analysis_stats,
    get_leadstech_data_for_banners,
)

# Scaling
from database.crud.scaling import (
    # Configs
    get_scaling_configs,
    get_scaling_config_by_id,
    get_enabled_scaling_configs,
    create_scaling_config,
    update_scaling_config,
    delete_scaling_config,
    update_scaling_config_last_run,
    # Config Accounts
    get_scaling_config_account_ids,
    set_scaling_config_accounts,
    # Manual Scaling Groups
    get_manual_scaling_groups,
    set_manual_scaling_groups,
    # Conditions
    get_scaling_conditions,
    create_scaling_condition,
    update_scaling_condition,
    delete_scaling_condition,
    delete_all_scaling_conditions,
    set_scaling_conditions,
    # Logs
    get_scaling_logs,
    create_scaling_log,
    # Logic
    check_group_conditions,
    # Tasks
    create_scaling_task,
    get_scaling_task,
    get_active_scaling_tasks,
    get_recent_scaling_tasks,
    start_scaling_task,
    update_scaling_task_progress,
    complete_scaling_task,
    cancel_scaling_task,
    cleanup_old_scaling_tasks,
)

# Disable Rules
from database.crud.disable_rules import (
    # Rules
    get_disable_rules,
    get_disable_rule_by_id,
    create_disable_rule,
    update_disable_rule,
    delete_disable_rule,
    # Conditions
    get_rule_conditions,
    add_rule_condition,
    update_rule_condition,
    delete_rule_condition,
    replace_rule_conditions,
    # Accounts
    get_rule_accounts,
    get_rule_account_ids,
    add_rule_account,
    remove_rule_account,
    replace_rule_accounts,
    get_rules_for_account,
    get_rules_for_account_by_vk_id,
    get_rules_for_account_by_name,
    # Logic
    check_banner_against_rules,
    format_rule_match_reason,
)


__all__ = [
    # Users
    "get_user_by_id",
    "get_user_by_email",
    "get_user_by_username",
    "create_user",
    "update_user",
    "update_user_password",
    "update_user_last_login",
    "delete_user",
    "get_all_users",
    "AVAILABLE_FEATURES",
    "get_user_features",
    "user_has_feature",
    "add_user_feature",
    "remove_user_feature",
    "set_user_features",
    "add_all_features_to_user",
    "create_refresh_token",
    "get_refresh_token_by_jti",
    "get_refresh_token_by_hash",
    "get_user_active_tokens",
    "update_token_last_used",
    "revoke_refresh_token",
    "revoke_all_user_tokens",
    "delete_expired_tokens",
    "delete_revoked_tokens",
    "get_user_setting",
    "set_user_setting",
    "get_all_user_settings",
    "delete_user_setting",
    # Accounts
    "get_accounts",
    "get_account_by_id",
    "get_account_by_db_id",
    "get_account_by_name",
    "create_account",
    "update_account",
    "update_account_label",
    "update_account_leadstech",
    "delete_account",
    # Settings
    "get_setting",
    "set_setting",
    "get_all_settings",
    "delete_setting",
    # Whitelist
    "get_whitelist",
    "add_to_whitelist",
    "remove_from_whitelist",
    "is_whitelisted",
    "replace_whitelist",
    "bulk_add_to_whitelist",
    "bulk_remove_from_whitelist",
    # Banners
    "create_banner_action",
    "log_disabled_banner",
    "get_banner_history",
    "get_disabled_banners",
    "get_disabled_banners_account_names",
    "get_active_banners",
    "add_active_banner",
    "remove_active_banner",
    "update_active_banner_stats",
    # Stats
    "get_process_state",
    "get_all_process_states",
    "set_process_running",
    "set_process_stopped",
    "update_process_status",
    "clear_all_process_states",
    "save_account_stats",
    "get_account_stats",
    "get_today_stats",
    "get_stats_by_date_range",
    "get_account_stats_summary",
    # LeadsTech
    "get_leadstech_config",
    "create_or_update_leadstech_config",
    "delete_leadstech_config",
    "get_leadstech_cabinets",
    "get_leadstech_cabinet_by_account",
    "create_leadstech_cabinet",
    "update_leadstech_cabinet",
    "delete_leadstech_cabinet",
    "save_leadstech_analysis_result",
    "replace_leadstech_analysis_results",
    "get_leadstech_analysis_results",
    "get_leadstech_analysis_cabinet_names",
    "get_leadstech_analysis_stats",
    "get_leadstech_data_for_banners",
    # Scaling
    "get_scaling_configs",
    "get_scaling_config_by_id",
    "get_enabled_scaling_configs",
    "create_scaling_config",
    "update_scaling_config",
    "delete_scaling_config",
    "update_scaling_config_last_run",
    "get_scaling_config_account_ids",
    "set_scaling_config_accounts",
    "get_manual_scaling_groups",
    "set_manual_scaling_groups",
    "get_scaling_conditions",
    "create_scaling_condition",
    "update_scaling_condition",
    "delete_scaling_condition",
    "delete_all_scaling_conditions",
    "set_scaling_conditions",
    "get_scaling_logs",
    "create_scaling_log",
    "check_group_conditions",
    "create_scaling_task",
    "get_scaling_task",
    "get_active_scaling_tasks",
    "get_recent_scaling_tasks",
    "start_scaling_task",
    "update_scaling_task_progress",
    "complete_scaling_task",
    "cancel_scaling_task",
    "cleanup_old_scaling_tasks",
    # Disable Rules
    "get_disable_rules",
    "get_disable_rule_by_id",
    "create_disable_rule",
    "update_disable_rule",
    "delete_disable_rule",
    "get_rule_conditions",
    "add_rule_condition",
    "update_rule_condition",
    "delete_rule_condition",
    "replace_rule_conditions",
    "get_rule_accounts",
    "get_rule_account_ids",
    "add_rule_account",
    "remove_rule_account",
    "replace_rule_accounts",
    "get_rules_for_account",
    "get_rules_for_account_by_vk_id",
    "get_rules_for_account_by_name",
    "check_banner_against_rules",
    "format_rule_match_reason",
]
