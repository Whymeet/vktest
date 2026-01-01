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
                        error_msg = result.get("error", "Unknown error")
                        crud.update_scaling_task_progress(
                            db, task_id,
                            last_error=error_msg,
                            add_error={
                                "message": error_msg,
                                "account": account_name,
                                "group_id": group_id,
                                "group_name": result.get("original_group_name")
                            }
                        )

                except Exception as e:
                    error_msg = str(e)
                    crud.create_scaling_log(
                        db,
                        user_id=user_id,
                        config_id=None,
                        config_name="Manual",
                        account_name=account_name,
                        original_group_id=group_id,
                        original_group_name=None,
                        success=False,
                        error_message=error_msg
                    )
                    failed += 1
                    crud.update_scaling_task_progress(
                        db, task_id,
                        last_error=error_msg,
                        add_error={
                            "message": error_msg,
                            "account": account_name,
                            "group_id": group_id,
                            "group_name": None
                        }
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
    """
    Background worker for auto-scaling configuration execution.
    Uses BannerScalingEngine for banner-level analysis and classification.
    """
    from services.scaling_engine import BannerScalingEngine
    from database.models import Account

    db = SessionLocal()
    try:
        print(f"[TASK {task_id}] Auto-scaling started for config: {config_name}")
        print(f"[TASK {task_id}] Using BannerScalingEngine for banner-level scaling")

        # Convert account tuples to Account-like objects
        class AccountWrapper:
            def __init__(self, account_id, name, api_token, label=None):
                self.id = account_id
                self.name = name
                self.api_token = api_token
                self.label = label

        account_objects = [
            AccountWrapper(acc[0], acc[1], acc[2], acc[3] if len(acc) > 3 else None)
            for acc in accounts
        ]

        # Create and run the banner scaling engine
        engine = BannerScalingEngine(
            config_id=config_id,
            user_id=user_id,
            task_id=task_id,
            db_session=db
        )

        result = engine.run(account_objects)

        # Update last run time
        crud.update_scaling_config_last_run(db, config_id)

        # Determine final status
        if result.failed_duplications == 0:
            final_status = 'completed'
        elif result.successful_duplications == 0:
            final_status = 'failed'
        else:
            final_status = 'completed'

        crud.complete_scaling_task(db, task_id, status=final_status)

        print(f"[TASK {task_id}] Auto-scaling completed:")
        print(f"  - Banners analyzed: {result.total_banners_analyzed}")
        print(f"  - Positive: {result.positive_banners}")
        print(f"  - Negative: {result.negative_banners}")
        print(f"  - Groups duplicated: {result.successful_duplications}")
        print(f"  - Failed: {result.failed_duplications}")

    except Exception as e:
        print(f"[TASK {task_id}] Fatal error in auto-scaling: {e}")
        import traceback
        traceback.print_exc()
        crud.complete_scaling_task(db, task_id, status='failed', last_error=str(e))
    finally:
        db.close()
