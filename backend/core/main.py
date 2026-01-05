"""
VK Ads Manager - Async version with parallel account processing.
Uses asyncio + aiohttp for true parallelism.
PostgreSQL database version.

This is the main entry point - orchestrates analysis across all accounts.
"""
import asyncio
import aiohttp
import sys
from pathlib import Path

# Add parent directory to path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, timedelta

from utils.logging_setup import setup_logging, get_logger
from database import init_db, SessionLocal
from database import crud

# Import core modules
from core.config_loader import (
    load_config_from_db,
    config_to_legacy_dict,
    get_extra_lookback_days,
    AnalysisConfig,
)
from core.analyzer import analyze_account
from core.telegram_notifier import send_analysis_notifications, send_error_notification
from core.results_exporter import save_analysis_results, get_results_totals
from core.db_logger import any_rules_require_roi

# Import LeadsTech modules for ROI loading
from leadstech.roi_loader import load_roi_data_parallel
from leadstech.leadstech_client import LeadstechClient, LeadstechClientConfig
from leadstech.vk_client import VkAdsClient, VkAdsConfig

# Initialize logging
setup_logging()
logger = get_logger(service="vk_api", function="auto_disable")

VK_API_BASE_URL = "https://ads.vk.com/api/v2"


def _load_roi_data_for_disable(user_id: int, date_from: str, date_to: str) -> dict:
    """
    Load ROI data from LeadsTech for auto-disable analysis.

    Args:
        user_id: User ID for loading LeadsTech config
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)

    Returns:
        Dict mapping banner_id to BannerROIData
    """
    db = SessionLocal()
    try:
        # Load LeadsTech config
        lt_config = crud.get_leadstech_config(db, user_id)
        if not lt_config:
            logger.warning("No LeadsTech config found, ROI conditions will use -100% default")
            return {}

        if not lt_config.login or not lt_config.password:
            logger.warning("LeadsTech credentials not configured")
            return {}

        # Get accounts with leadstech_enabled
        accounts_list = crud.get_accounts(db, user_id)
        accounts_with_lt = [a for a in accounts_list if a.leadstech_enabled and a.label]

        if not accounts_with_lt:
            logger.warning("No accounts with LeadsTech enabled")
            return {}

        # Get banner sub fields from config
        banner_sub_fields = lt_config.banner_sub_fields or ["sub4", "sub5"]
        if isinstance(banner_sub_fields, str):
            import json
            try:
                banner_sub_fields = json.loads(banner_sub_fields)
            except (json.JSONDecodeError, TypeError):
                banner_sub_fields = [banner_sub_fields]

        logger.info(f"Loading ROI data from LeadsTech for {len(accounts_with_lt)} accounts")
        logger.info(f"Date range: {date_from} to {date_to}")
        logger.info(f"Banner sub fields: {banner_sub_fields}")

        # Create LeadsTech client
        lt_client = LeadstechClient(LeadstechClientConfig(
            base_url=lt_config.base_url or "https://api.leads.tech",
            login=lt_config.login,
            password=lt_config.password,
            banner_sub_fields=banner_sub_fields
        ))

        # Factory to create VK client for each account
        def vk_client_factory(account):
            return VkAdsClient(VkAdsConfig(
                base_url=VK_API_BASE_URL,
                api_token=account.api_token
            ))

        # Load ROI data (PARALLEL version for better performance)
        roi_data = load_roi_data_parallel(
            lt_client=lt_client,
            vk_client_factory=vk_client_factory,
            accounts=accounts_with_lt,
            date_from=date_from,
            date_to=date_to,
            banner_sub_fields=banner_sub_fields,
            progress_callback=lambda msg: logger.info(msg),
            cancel_check_fn=None,
            max_workers=5  # Process up to 5 accounts in parallel per label
        )

        logger.info(f"Loaded ROI data for {len(roi_data)} banners")
        return roi_data

    except Exception as e:
        logger.error(f"Failed to load LeadsTech ROI data: {e}")
        logger.exception("ROI loading error details:")
        return {}
    finally:
        db.close()


async def main_async():
    """Main async function - orchestrates the analysis"""
    try:
        # Initialize database
        init_db()

        # Load configuration from DB
        config = load_config_from_db()
        legacy_config = config_to_legacy_dict(config)

        # Determine analysis type
        extra_days = get_extra_lookback_days()
        base_lookback = config.settings.lookback_days

        if extra_days > 0:
            analysis_type = f"EXTENDED ANALYSIS (+{extra_days} days to base {base_lookback})"
        else:
            analysis_type = "STANDARD ANALYSIS"

        logger.info(analysis_type)
        logger.info("VK Ads Manager - ASYNC VERSION")

        accounts = config.accounts
        logger.info(f"Loaded accounts: {len(accounts)}")
        logger.info(f"Account list: {list(accounts.keys())}")
        logger.info(f"Whitelist size: {len(config.whitelist)}")

        # Calculate analysis date range
        effective_lookback = config.get_effective_lookback_days(extra_days)
        today = date.today()
        date_from = (today - timedelta(days=effective_lookback)).isoformat()
        date_to = today.isoformat()

        # Check if any rules require ROI and load LeadsTech data
        roi_data = None
        if any_rules_require_roi(config.user_id):
            logger.info("=" * 80)
            logger.info("ROI CONDITIONS DETECTED - Loading LeadsTech data...")
            logger.info("=" * 80)
            roi_data = _load_roi_data_for_disable(config.user_id, date_from, date_to)
            if roi_data:
                logger.info(f"ROI data loaded successfully: {len(roi_data)} banners")
            else:
                logger.warning("No ROI data loaded - banners without LeadsTech data will have ROI=-100%")
        else:
            logger.info("No ROI conditions in rules - skipping LeadsTech data loading")

        # Create aiohttp session for all requests
        connector = aiohttp.TCPConnector(limit=20)  # Limit concurrent connections
        async with aiohttp.ClientSession(connector=connector) as session:

            # Create tasks for ALL accounts
            tasks = []
            for account_name, account_cfg in accounts.items():
                access_token = account_cfg.api_token
                if not access_token:
                    logger.error(f"No API token configured for account {account_name}")
                    continue

                # Create task for account analysis
                task = asyncio.create_task(
                    analyze_account(
                        session=session,
                        account_name=account_name,
                        access_token=access_token,
                        config=config,
                        account_trigger_id=account_cfg.trigger_id,
                        roi_data=roi_data
                    ),
                    name=f"analyze_{account_name}"
                )
                tasks.append(task)

            logger.info(f"Launching {len(tasks)} accounts IN PARALLEL")
            logger.info("=" * 80)

            # Run ALL accounts in parallel and wait for completion
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            all_results = []
            for i, result in enumerate(results):
                task_name = tasks[i].get_name()

                if isinstance(result, Exception):
                    logger.error(f"Error in task {task_name}: {result}")
                    continue

                if not result:
                    logger.warning(f"Task {task_name} returned empty result")
                    continue

                all_results.append(result)
                logger.info(
                    f"Completed account '{result['account_name']}': "
                    f"{len(result.get('over_limit', []))} unprofitable, "
                    f"{len(result.get('under_limit', []))} effective"
                )

        if not all_results:
            logger.error("No accounts were successfully analyzed")
            await send_error_notification(
                legacy_config,
                "Analysis failed: all accounts returned errors"
            )
            return

        # Calculate totals
        totals = get_results_totals(all_results)

        # Final statistics
        logger.info("=" * 80)
        logger.info("FINAL SUMMARY ACROSS ALL ACCOUNTS:")
        logger.info(f"Total unprofitable banners: {totals['unprofitable']}")
        logger.info(f"Total effective banners: {totals['effective']}")
        logger.info(f"Total testing/inactive: {totals['testing']}")
        logger.info(f"Total spent: {totals['spent']:.2f}₽")
        logger.info(f"Total VK goals: {int(totals['goals'])}")
        if totals['goals'] > 0:
            logger.info(f"Average cost per goal: {totals['spent'] / totals['goals']:.2f}₽")
        logger.info("=" * 80)

        # Save results to files
        project_root = Path(__file__).parent.parent
        data_dir = project_root / "data"
        save_analysis_results(
            results=all_results,
            output_dir=data_dir,
            spent_limit_rub=config.settings.spent_limit_rub,
            total_accounts=len(accounts)
        )

        # Send Telegram notifications
        logger.info("=" * 80)
        logger.info("SENDING TELEGRAM NOTIFICATIONS")
        logger.info("=" * 80)

        effective_lookback = config.get_effective_lookback_days(extra_days)
        await send_analysis_notifications(legacy_config, all_results, effective_lookback)

        logger.info("=" * 80)
        logger.info("ANALYSIS COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)

    except KeyboardInterrupt:
        logger.warning("Received user interrupt (Ctrl+C)")
        logger.info("Work terminated by user request")
    except Exception as e:
        logger.error(f"CRITICAL ERROR: {e}")
        logger.exception("Error details:")
        try:
            config = load_config_from_db()
            legacy_config = config_to_legacy_dict(config)
            await send_error_notification(legacy_config, f"Critical error: {e}")
        except Exception:
            pass
        raise


def main():
    """Entry point - runs async main"""
    asyncio.run(main_async())


# ===================== ENTRY POINT =====================

if __name__ == "__main__":
    main()
