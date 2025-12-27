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

from utils.logging_setup import setup_logging, get_logger
from database import init_db

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

# Initialize logging
setup_logging()
logger = get_logger(service="vk_api", function="auto_disable")


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
                        account_trigger_id=account_cfg.trigger_id
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
