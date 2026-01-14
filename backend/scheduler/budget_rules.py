"""
Scheduler module for running budget rules analysis
"""
import asyncio
import aiohttp
from typing import Optional, Callable
from sqlalchemy.orm import Session

from database import crud
from database.models import Account
from core.budget_changer import process_budget_rules_for_account
from scheduler.event_logger import log_scheduler_event, EventType
from utils.logging_setup import get_logger

logger = get_logger(service="scheduler", function="budget_rules")


def run_budget_rules_analysis(
    db: Session,
    user_id: int,
    username: str,
    budget_settings: dict,
    analysis_settings: dict,
    should_stop_fn: Optional[Callable[[], bool]] = None,
    run_count: int = 0,
    logger_override=None
) -> dict:
    """
    Run budget rules analysis for all accounts.
    
    Args:
        db: Database session
        user_id: User ID
        username: Username for logging
        budget_settings: Budget rules settings from user settings
        analysis_settings: Analysis settings (for dry_run, etc.)
        should_stop_fn: Function to check if should stop
        run_count: Current run count
        logger_override: Optional custom logger
    
    Returns:
        dict with results summary
    """
    log = logger_override or logger
    
    if not budget_settings.get("enabled", False):
        log.info("Budget rules are disabled in settings")
        return {"skipped": True, "reason": "disabled"}
    
    dry_run = budget_settings.get("dry_run", True)
    
    log.info("=" * 80)
    log.info("BUDGET RULES ANALYSIS")
    log.info(f"   User: {username} (ID: {user_id})")
    log.info(f"   Dry run: {dry_run}")
    log.info("=" * 80)
    
    # Get all user accounts
    accounts = crud.get_accounts(db, user_id)
    if not accounts:
        log.warning("No accounts found for user")
        return {"skipped": True, "reason": "no_accounts"}
    
    log.info(f"Found {len(accounts)} accounts")
    
    # Get whitelist
    whitelist = crud.get_whitelist(db, user_id)
    whitelist_set = set(whitelist)
    log.info(f"Whitelist: {len(whitelist_set)} banners")
    
    # Run async processing
    results = asyncio.run(_run_budget_rules_async(
        accounts=accounts,
        user_id=user_id,
        dry_run=dry_run,
        whitelist=whitelist_set,
        should_stop_fn=should_stop_fn,
        logger=log
    ))
    
    # Summary
    total_changes = sum(r.get("total_changes", 0) for r in results)
    successful = sum(r.get("successful", 0) for r in results)
    failed = sum(r.get("failed", 0) for r in results)
    
    log.info("=" * 80)
    log.info("BUDGET RULES ANALYSIS COMPLETE")
    log.info(f"   Accounts processed: {len(results)}")
    log.info(f"   Total budget changes: {total_changes}")
    log.info(f"   Successful: {successful}")
    log.info(f"   Failed: {failed}")
    log.info(f"   Dry run: {dry_run}")
    log.info("=" * 80)
    
    # Log event
    log_scheduler_event(
        EventType.ANALYSIS_SUCCESS,
        f"Budget rules analysis completed: {total_changes} changes",
        username=username,
        user_id=str(user_id),
        run_count=run_count,
        extra_data={
            "total_changes": total_changes,
            "successful": successful,
            "failed": failed,
            "dry_run": dry_run,
            "accounts_processed": len(results)
        }
    )
    
    return {
        "results": results,
        "total_changes": total_changes,
        "successful": successful,
        "failed": failed,
        "dry_run": dry_run
    }


async def _run_budget_rules_async(
    accounts: list,
    user_id: int,
    dry_run: bool,
    whitelist: set,
    should_stop_fn: Optional[Callable[[], bool]] = None,
    logger=None
) -> list:
    """
    Async runner for budget rules processing.
    """
    log = logger or globals()["logger"]
    results = []
    
    base_url = "https://ads.vk.com/api/v2"
    
    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        for account in accounts:
            if should_stop_fn and should_stop_fn():
                log.warning("Budget rules analysis stopped by signal")
                break
            
            account_name = account.name
            access_token = account.api_token
            
            if not access_token:
                log.warning(f"No API token for account {account_name}")
                continue
            
            try:
                result = await process_budget_rules_for_account(
                    session=session,
                    account_name=account_name,
                    access_token=access_token,
                    base_url=base_url,
                    user_id=user_id,
                    dry_run=dry_run,
                    whitelist=whitelist
                )
                results.append(result)
                
            except Exception as e:
                log.error(f"Error processing budget rules for {account_name}: {e}")
                import traceback
                log.error(traceback.format_exc())
                results.append({
                    "account_name": account_name,
                    "error": str(e),
                    "total_changes": 0,
                    "successful": 0,
                    "failed": 0
                })
            
            # Small delay between accounts
            await asyncio.sleep(1)
    
    return results
