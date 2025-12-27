"""
Scaling background workers - duplication and auto-scaling tasks
"""
from typing import Optional, List

from database import crud, SessionLocal


def run_duplication_task(
    task_id: int,
    user_id: int,
    account_token: str,
    account_name: str,
    ad_group_ids: List[int],
    duplicates_count: int,
    new_budget: Optional[float],
    new_name: Optional[str],
    auto_activate: bool
):
    """Background worker for duplication task"""
    from utils.vk_api import duplicate_ad_group_full

    db = SessionLocal()
    try:
        crud.start_scaling_task(db, task_id)

        base_url = "https://ads.vk.com/api/v2"
        completed = 0
        successful = 0
        failed = 0

        for group_id in ad_group_ids:
            task = crud.get_scaling_task(db, task_id)
            if task and task.status == 'cancelled':
                print(f"[TASK {task_id}] Task was cancelled, stopping...")
                break

            for copy_num in range(duplicates_count):
                task = crud.get_scaling_task(db, task_id)
                if task and task.status == 'cancelled':
                    break

                try:
                    crud.update_scaling_task_progress(
                        db, task_id,
                        current_group_id=group_id,
                        current_group_name=f"Group {group_id} (copy {copy_num + 1})"
                    )

                    result = duplicate_ad_group_full(
                        token=account_token,
                        base_url=base_url,
                        ad_group_id=group_id,
                        new_name=new_name,
                        new_budget=new_budget,
                        auto_activate=auto_activate,
                        rate_limit_delay=0.03
                    )

                    banner_ids_data = None
                    if result.get("duplicated_banners"):
                        banner_ids_data = [
                            {
                                "original_id": b.get("original_id"),
                                "new_id": b.get("new_id"),
                                "name": b.get("name")
                            }
                            for b in result.get("duplicated_banners", [])
                        ]

                    crud.create_scaling_log(
                        db,
                        user_id=user_id,
                        config_id=None,
                        config_name="Manual",
                        account_name=account_name,
                        original_group_id=group_id,
                        original_group_name=result.get("original_group_name"),
                        new_group_id=result.get("new_group_id"),
                        new_group_name=result.get("new_group_name"),
                        stats_snapshot=None,
                        success=result.get("success", False),
                        error_message=result.get("error"),
                        total_banners=result.get("total_banners", 0),
                        duplicated_banners=len(result.get("duplicated_banners", [])),
                        duplicated_banner_ids=banner_ids_data,
                        requested_name=new_name
                    )

                    if result.get("success"):
                        successful += 1
                    else:
                        failed += 1
                        crud.update_scaling_task_progress(
                            db, task_id,
                            last_error=result.get("error", "Unknown error")
                        )

                except Exception as e:
                    crud.create_scaling_log(
                        db,
                        user_id=user_id,
                        config_id=None,
                        config_name="Manual",
                        account_name=account_name,
                        original_group_id=group_id,
                        original_group_name=None,
                        success=False,
                        error_message=str(e)
                    )
                    failed += 1
                    crud.update_scaling_task_progress(
                        db, task_id,
                        last_error=str(e)
                    )

                completed += 1
                crud.update_scaling_task_progress(
                    db, task_id,
                    completed=completed,
                    successful=successful,
                    failed=failed
                )

        final_status = 'completed' if failed == 0 else ('failed' if successful == 0 else 'completed')
        crud.complete_scaling_task(db, task_id, status=final_status)
        print(f"[TASK {task_id}] Completed: {successful} success, {failed} failed")

    except Exception as e:
        print(f"[TASK {task_id}] Fatal error: {e}")
        crud.complete_scaling_task(db, task_id, status='failed', last_error=str(e))
    finally:
        db.close()


def run_auto_scaling_task(
    task_id: int,
    user_id: int,
    config_id: int,
    config_name: str,
    conditions: list,
    accounts: list,
    lookback_days: int,
    duplicates_count: int,
    new_budget: float,
    new_name: Optional[str],
    auto_activate: bool
):
    """Background worker for auto-scaling configuration execution"""
    from datetime import datetime, timedelta
    from utils.vk_api import get_ad_groups_with_stats, duplicate_ad_group_full

    class SimpleCondition:
        def __init__(self, metric, operator, value):
            self.metric = metric
            self.operator = operator
            self.value = value

    db = SessionLocal()
    try:
        crud.start_scaling_task(db, task_id)
        print(f"[TASK {task_id}] Auto-scaling started for config: {config_name}")

        condition_objects = [
            SimpleCondition(c['metric'], c['operator'], c['value'])
            for c in conditions
        ]

        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        base_url = "https://ads.vk.com/api/v2"

        completed = 0
        successful = 0
        failed = 0

        print(f"[TASK {task_id}] Processing {len(accounts)} accounts, lookback: {lookback_days} days")

        for account_id, account_name, account_token in accounts:
            try:
                print(f"[TASK {task_id}] Fetching ad groups for account: {account_name}")

                groups = get_ad_groups_with_stats(
                    token=account_token,
                    base_url=base_url,
                    date_from=date_from,
                    date_to=date_to
                )

                print(f"[TASK {task_id}] Found {len(groups)} groups in {account_name}")

                for group in groups:
                    group_id = group.get("id")
                    group_name = group.get("name", "Unknown")
                    stats = group.get("stats", {})

                    conditions_met = crud.check_group_conditions(stats, condition_objects)

                    if conditions_met:
                        print(f"[TASK {task_id}] Conditions met for group {group_id}: {group_name}")

                        for dup_num in range(1, duplicates_count + 1):
                            task_check = crud.get_scaling_task(db, task_id)
                            if task_check and task_check.status == 'cancelled':
                                print(f"[TASK {task_id}] Task was cancelled, stopping...")
                                raise Exception("CANCELLED")

                            try:
                                crud.update_scaling_task_progress(
                                    db, task_id,
                                    current_group_id=group_id,
                                    current_group_name=f"{group_name} (copy {dup_num}/{duplicates_count})"
                                )

                                result = duplicate_ad_group_full(
                                    token=account_token,
                                    base_url=base_url,
                                    ad_group_id=group_id,
                                    new_name=new_name,
                                    new_budget=new_budget,
                                    auto_activate=auto_activate,
                                    rate_limit_delay=0.03
                                )

                                banner_ids_data = None
                                if result.get("duplicated_banners"):
                                    banner_ids_data = [
                                        {
                                            "original_id": b.get("original_id"),
                                            "new_id": b.get("new_id"),
                                            "name": b.get("name")
                                        }
                                        for b in result.get("duplicated_banners", [])
                                    ]

                                crud.create_scaling_log(
                                    db,
                                    user_id=user_id,
                                    config_id=config_id,
                                    config_name=config_name,
                                    account_name=account_name,
                                    original_group_id=group_id,
                                    original_group_name=group_name,
                                    new_group_id=result.get("new_group_id"),
                                    new_group_name=result.get("new_group_name"),
                                    stats_snapshot=stats,
                                    success=result.get("success", False),
                                    error_message=result.get("error"),
                                    total_banners=result.get("total_banners", 0),
                                    duplicated_banners=len(result.get("duplicated_banners", [])),
                                    duplicated_banner_ids=banner_ids_data,
                                    requested_name=new_name
                                )

                                if result.get("success"):
                                    successful += 1
                                    print(f"[TASK {task_id}] Successfully duplicated {group_id} ({dup_num}/{duplicates_count})")
                                else:
                                    failed += 1
                                    crud.update_scaling_task_progress(
                                        db, task_id,
                                        last_error=result.get("error", "Unknown error")
                                    )
                                    print(f"[TASK {task_id}] Failed to duplicate {group_id}: {result.get('error')}")

                            except Exception as e:
                                failed += 1
                                crud.update_scaling_task_progress(
                                    db, task_id,
                                    last_error=str(e)
                                )
                                print(f"[TASK {task_id}] Error duplicating group {group_id}: {e}")

                            completed += 1
                            crud.update_scaling_task_progress(
                                db, task_id,
                                completed=completed,
                                successful=successful,
                                failed=failed
                            )

            except Exception as e:
                if str(e) == "CANCELLED":
                    raise
                print(f"[TASK {task_id}] Error processing account {account_name}: {e}")
                crud.update_scaling_task_progress(
                    db, task_id,
                    last_error=f"Account {account_name}: {str(e)}"
                )

        crud.update_scaling_config_last_run(db, config_id)

        final_status = 'completed' if failed == 0 else ('failed' if successful == 0 else 'completed')
        crud.complete_scaling_task(db, task_id, status=final_status)
        print(f"[TASK {task_id}] Auto-scaling completed: {successful} success, {failed} failed")

    except Exception as e:
        if str(e) == "CANCELLED":
            print(f"[TASK {task_id}] Auto-scaling cancelled by user")
        else:
            print(f"[TASK {task_id}] Fatal error in auto-scaling: {e}")
            crud.complete_scaling_task(db, task_id, status='failed', last_error=str(e))
    finally:
        db.close()
