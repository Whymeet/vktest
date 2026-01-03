#!/usr/bin/env python3
"""
VK Ads Manager Scheduler - Automatic ad group analysis scheduler
PostgreSQL database version

Works in multiple passes:
1. Standard analysis with configured lookback_days
2. Extended analysis with random lookback days addition
3. Auto-reenable disabled banners (if enabled)
"""
import os
import sys
import time
import signal
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.time_utils import get_moscow_time
from utils.logging_setup import setup_logging, get_logger
from database import SessionLocal, init_db
from database import crud

# Import scheduler modules
from scheduler.config import (
    MAIN_SCRIPT,
    LOGS_DIR,
    SCHEDULER_LOGS_DIR,
    EXTRA_LOOKBACK_DAYS_MIN,
    EXTRA_LOOKBACK_DAYS_MAX,
    get_default_settings,
)
from scheduler.event_logger import log_scheduler_event, EventType
from scheduler.analysis import run_analysis
from scheduler.reenable import run_reenable_analysis
from scheduler.roi_reenable import run_roi_reenable_analysis

# Initialize logging
setup_logging()


class VKAdsScheduler:
    """Scheduler for automatic VK Ads Manager runs"""

    def __init__(self):
        """Initialize scheduler"""
        # Get user_id and username before setting up logging
        self.user_id = os.environ.get('VK_ADS_USER_ID')
        self.username = os.environ.get('VK_ADS_USERNAME', 'unknown')

        self.setup_logging()
        self.load_settings()

        # Scheduler state
        self.is_running = False
        self.should_stop = False
        self.last_run_time: Optional[datetime] = None
        self.next_run_time: Optional[datetime] = None
        self.run_count = 0
        self.last_reenable_time: Optional[datetime] = None
        self.last_roi_reenable_time: Optional[datetime] = None

        # Signal handling for graceful shutdown
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

        self.logger.info("VK Ads Scheduler initialized")
        self.logger.info(f"User: {self.username} (ID: {self.user_id})")
        self.logger.info(f"Main script: {MAIN_SCRIPT}")

        # Log scheduler start
        log_scheduler_event(
            EventType.STARTED,
            "Scheduler started",
            username=self.username,
            user_id=self.user_id,
            run_count=0
        )

    def handle_signal(self, signum, frame):
        """Handle signals for graceful shutdown"""
        signal_names = {
            signal.SIGTERM: "SIGTERM",
            signal.SIGINT: "SIGINT",
            9: "SIGKILL"
        }
        signal_name = signal_names.get(signum, f"SIGNAL_{signum}")

        self.logger.warning(f"Received signal {signal_name} ({signum}), shutting down...")
        log_scheduler_event(
            EventType.SIGNAL_RECEIVED,
            f"Received signal {signal_name} ({signum})",
            username=self.username,
            user_id=self.user_id,
            run_count=self.run_count
        )

        self.should_stop = True

    def setup_logging(self):
        """Setup logging with per-user files via loguru"""
        LOGS_DIR.mkdir(exist_ok=True)
        SCHEDULER_LOGS_DIR.mkdir(exist_ok=True)

        user_id_int = int(self.user_id) if self.user_id else None
        self.logger = get_logger(service="scheduler", function="auto_disable", user_id=user_id_int)

        timestamp = get_moscow_time().strftime("%Y%m%d")
        log_file = SCHEDULER_LOGS_DIR / f"scheduler_{self.username}_{timestamp}.log"
        self.logger.info(f"Logging to file: {log_file}")

    def load_settings(self):
        """Load settings from DB for current user"""
        user_id = os.environ.get('VK_ADS_USER_ID')
        if not user_id:
            self.logger.warning("VK_ADS_USER_ID not set, using defaults")
            self.settings = get_default_settings()
            return

        user_id = int(user_id)

        db = SessionLocal()
        try:
            settings = crud.get_user_setting(db, user_id, 'scheduler')
            if settings:
                self.settings = settings
                # Ensure reenable settings exist
                if "reenable" not in self.settings:
                    self.settings["reenable"] = {
                        "enabled": False,
                        "interval_minutes": 120,
                        "lookback_hours": 24,
                        "delay_after_analysis_seconds": 30,
                        "dry_run": True
                    }
                elif "interval_minutes" not in self.settings["reenable"]:
                    self.settings["reenable"]["interval_minutes"] = 120
                # Ensure roi_reenable settings exist
                if "roi_reenable" not in self.settings:
                    self.settings["roi_reenable"] = {
                        "enabled": False,
                        "interval_minutes": 60,
                        "lookback_days": 7,
                        "roi_threshold": 50.0,
                        "account_ids": [],
                        "dry_run": True,
                        "delay_after_analysis_seconds": 30
                    }
            else:
                self.settings = get_default_settings()
                crud.set_user_setting(db, user_id, 'scheduler', self.settings)
        finally:
            db.close()

    def reload_settings(self):
        """Reload settings from DB"""
        self.load_settings()
        self.logger.debug("Settings reloaded")

    def is_quiet_hours(self) -> bool:
        """Check if currently in quiet hours"""
        quiet_hours = self.settings.get("quiet_hours", {})
        if not quiet_hours.get("enabled", False):
            return False

        try:
            now = get_moscow_time()
            start = datetime.strptime(quiet_hours.get("start", "23:00"), "%H:%M").time()
            end = datetime.strptime(quiet_hours.get("end", "08:00"), "%H:%M").time()
            current_time = now.time()

            # Check for midnight crossing
            if start > end:
                return current_time >= start or current_time < end
            else:
                return start <= current_time < end
        except Exception as e:
            self.logger.error(f"Error checking quiet hours: {e}")
            return False

    def _should_stop(self) -> bool:
        """Callback for checking if should stop (used by submodules)"""
        return self.should_stop

    def run_double_analysis(self) -> bool:
        """Run double analysis: standard + extended + auto-reenable + ROI reenable (by intervals)"""
        reenable_settings = self.settings.get("reenable", {})
        reenable_enabled = reenable_settings.get("enabled", False)
        reenable_interval = reenable_settings.get("interval_minutes", 120)

        roi_reenable_settings = self.settings.get("roi_reenable", {})
        roi_reenable_enabled = roi_reenable_settings.get("enabled", False)
        roi_reenable_interval = roi_reenable_settings.get("interval_minutes", 60)

        # Check if it's time to run reenable
        should_run_reenable = False
        if reenable_enabled:
            if self.last_reenable_time is None:
                should_run_reenable = False
                self.logger.info(f"Reenable: first run, will execute in {reenable_interval} min")
            else:
                minutes_since_reenable = (get_moscow_time() - self.last_reenable_time).total_seconds() / 60
                if minutes_since_reenable >= reenable_interval:
                    should_run_reenable = True
                    self.logger.info(
                        f"Reenable: {minutes_since_reenable:.0f} min passed "
                        f"(interval {reenable_interval} min) -> WILL RUN"
                    )
                else:
                    remaining = reenable_interval - minutes_since_reenable
                    self.logger.info(f"Reenable: {remaining:.0f} min until next run")

        # Check if it's time to run ROI reenable
        should_run_roi_reenable = False
        if roi_reenable_enabled:
            if self.last_roi_reenable_time is None:
                should_run_roi_reenable = False
                self.logger.info(f"ROI Reenable: first run, will execute in {roi_reenable_interval} min")
            else:
                minutes_since_roi_reenable = (get_moscow_time() - self.last_roi_reenable_time).total_seconds() / 60
                if minutes_since_roi_reenable >= roi_reenable_interval:
                    should_run_roi_reenable = True
                    self.logger.info(
                        f"ROI Reenable: {minutes_since_roi_reenable:.0f} min passed "
                        f"(interval {roi_reenable_interval} min) -> WILL RUN"
                    )
                else:
                    remaining = roi_reenable_interval - minutes_since_roi_reenable
                    self.logger.info(f"ROI Reenable: {remaining:.0f} min until next run")

        total_passes = 2 + (1 if should_run_reenable else 0) + (1 if should_run_roi_reenable else 0)

        # Pass 1: standard analysis
        self.logger.info(f"PASS 1/{total_passes}: Standard analysis")
        success1, _ = run_analysis(
            extra_lookback_days=0,
            run_type="main",
            username=self.username,
            user_id=self.user_id,
            run_count=self.run_count,
            logger=self.logger
        )

        if self.should_stop:
            return success1

        # Pause between passes
        self.logger.info("Pause 10 sec between passes...")
        time.sleep(10)

        if self.should_stop:
            return success1

        # Pass 2: extended analysis with random extra days
        extra_days = random.randint(EXTRA_LOOKBACK_DAYS_MIN, EXTRA_LOOKBACK_DAYS_MAX)
        self.logger.info(f"PASS 2/{total_passes}: Extended analysis (+{extra_days} days)")
        success2, _ = run_analysis(
            extra_lookback_days=extra_days,
            run_type="extended",
            username=self.username,
            user_id=self.user_id,
            run_count=self.run_count,
            logger=self.logger
        )

        if success1 and success2:
            self.logger.info("Both analyses completed successfully!")
        elif success1:
            self.logger.warning("Standard analysis succeeded, extended failed")
        elif success2:
            self.logger.warning("Extended analysis succeeded, standard failed")
        else:
            self.logger.error("Both analyses failed")

        # Pass 3: auto-reenable (only if interval passed)
        current_pass = 3
        if should_run_reenable and not self.should_stop:
            delay = reenable_settings.get("delay_after_analysis_seconds", 30)
            self.logger.info(f"Pause {delay} sec before reenable...")
            time.sleep(delay)

            if not self.should_stop:
                self.logger.info(f"PASS {current_pass}/{total_passes}: Auto-reenable")
                self._run_reenable()
                self.last_reenable_time = get_moscow_time()
                self.logger.info(f"Next reenable in {reenable_interval} min")
                current_pass += 1

        # Pass 4: ROI auto-reenable (only if interval passed)
        if should_run_roi_reenable and not self.should_stop:
            delay = roi_reenable_settings.get("delay_after_analysis_seconds", 30)
            self.logger.info(f"Pause {delay} sec before ROI reenable...")
            time.sleep(delay)

            if not self.should_stop:
                self.logger.info(f"PASS {current_pass}/{total_passes}: ROI Auto-reenable")
                self._run_roi_reenable()
                self.last_roi_reenable_time = get_moscow_time()
                self.logger.info(f"Next ROI reenable in {roi_reenable_interval} min")

        # Initialize times for first run
        if reenable_enabled and self.last_reenable_time is None:
            self.last_reenable_time = get_moscow_time()
        if roi_reenable_enabled and self.last_roi_reenable_time is None:
            self.last_roi_reenable_time = get_moscow_time()

        return success1 or success2

    def _run_reenable(self):
        """Run reenable analysis with current settings"""
        user_id = int(self.user_id) if self.user_id else None
        if not user_id:
            self.logger.error("user_id not set, reenable not possible")
            return

        reenable_settings = self.settings.get("reenable", {})

        db = SessionLocal()
        try:
            analysis_settings = crud.get_user_setting(db, user_id, 'analysis_settings') or {}
            telegram_config = crud.get_user_setting(db, user_id, 'telegram') or {}

            run_reenable_analysis(
                db=db,
                user_id=user_id,
                username=self.username,
                reenable_settings=reenable_settings,
                analysis_settings=analysis_settings,
                telegram_config=telegram_config,
                should_stop_fn=self._should_stop,
                run_count=self.run_count,
                logger=self.logger
            )
        except Exception as e:
            self.logger.error(f"Critical reenable error: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

            log_scheduler_event(
                EventType.REENABLE_ERROR,
                f"Reenable exception: {e}",
                username=self.username,
                user_id=str(user_id),
                run_count=self.run_count,
                extra_data={"exception": str(e)}
            )
        finally:
            db.close()

    def _run_roi_reenable(self):
        """Run ROI-based reenable analysis with current settings"""
        user_id = int(self.user_id) if self.user_id else None
        if not user_id:
            self.logger.error("user_id not set, ROI reenable not possible")
            return

        roi_reenable_settings = self.settings.get("roi_reenable", {})

        db = SessionLocal()
        try:
            telegram_config = crud.get_user_setting(db, user_id, 'telegram') or {}

            run_roi_reenable_analysis(
                db=db,
                user_id=user_id,
                username=self.username,
                roi_reenable_settings=roi_reenable_settings,
                telegram_config=telegram_config,
                should_stop_fn=self._should_stop,
                run_count=self.run_count,
                logger=self.logger
            )
        except Exception as e:
            self.logger.error(f"Critical ROI reenable error: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

            log_scheduler_event(
                EventType.REENABLE_ERROR,
                f"ROI Reenable exception: {e}",
                username=self.username,
                user_id=str(user_id),
                run_count=self.run_count,
                extra_data={"exception": str(e), "type": "roi_reenable"}
            )
        finally:
            db.close()

    def calculate_next_run(self) -> datetime:
        """Calculate next run time"""
        interval = self.settings.get("interval_minutes", 60)
        self.next_run_time = get_moscow_time() + timedelta(minutes=interval)
        return self.next_run_time

    def run(self):
        """Main scheduler loop"""
        self.is_running = True
        max_runs = self.settings.get("max_runs", 0)
        start_delay = self.settings.get("start_delay_seconds", 10)

        self.logger.info("=" * 60)
        self.logger.info("VK Ads Scheduler started")
        interval = self.settings.get('interval_minutes', 60)
        if interval < 1:
            interval_str = f"{interval * 60:.0f} sec"
        else:
            interval_str = f"{interval} min"
        self.logger.info(f"   Interval: {interval_str}")
        self.logger.info(f"   Max runs: {max_runs if max_runs > 0 else 'unlimited'}")
        self.logger.info("=" * 60)

        log_scheduler_event(
            EventType.SCHEDULER_LOOP_STARTED,
            "Main loop started",
            username=self.username,
            user_id=self.user_id,
            run_count=0,
            extra_data={
                "interval_minutes": self.settings.get('interval_minutes', 60),
                "max_runs": max_runs,
                "start_delay_seconds": start_delay
            }
        )

        # Initial delay
        if start_delay > 0:
            self.logger.info(f"Initial delay {start_delay} sec...")
            time.sleep(start_delay)

        while not self.should_stop:
            # Reload settings before each run
            self.reload_settings()

            # Check run limit
            if max_runs > 0 and self.run_count >= max_runs:
                self.logger.info(f"Run limit reached ({max_runs})")
                log_scheduler_event(
                    EventType.MAX_RUNS_REACHED,
                    f"Run limit reached: {max_runs}",
                    username=self.username,
                    user_id=self.user_id,
                    run_count=self.run_count
                )
                break

            # Check quiet hours
            if self.is_quiet_hours():
                self.logger.info("Quiet hours, skipping run")
                self.calculate_next_run()
                self._sleep_until_next_run()
                continue

            # Run double analysis
            self.run_count += 1
            self.last_run_time = get_moscow_time()
            self.logger.info(f"Run #{self.run_count}")

            success = self.run_double_analysis()

            # Error handling with retries
            if not success and self.settings.get("retry_on_error", True):
                max_retries = self.settings.get("max_retries", 3)
                retry_delay = self.settings.get("retry_delay_minutes", 5)

                log_scheduler_event(
                    EventType.RETRY_STARTED,
                    f"Starting retries (max: {max_retries})",
                    username=self.username,
                    user_id=self.user_id,
                    run_count=self.run_count
                )

                for retry in range(1, max_retries + 1):
                    if self.should_stop:
                        break
                    self.logger.info(f"Retry {retry}/{max_retries} in {retry_delay} min...")
                    time.sleep(retry_delay * 60)

                    retry_success, _ = run_analysis(
                        username=self.username,
                        user_id=self.user_id,
                        run_count=self.run_count,
                        logger=self.logger
                    )
                    if retry_success:
                        log_scheduler_event(
                            EventType.RETRY_SUCCESS,
                            f"Retry {retry}/{max_retries} successful",
                            username=self.username,
                            user_id=self.user_id,
                            run_count=self.run_count
                        )
                        break
                else:
                    log_scheduler_event(
                        EventType.RETRY_FAILED,
                        f"All {max_retries} retries failed",
                        username=self.username,
                        user_id=self.user_id,
                        run_count=self.run_count
                    )

            # Calculate next run
            self.calculate_next_run()
            self.logger.info(f"Next run: {self.next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # Wait until next run
            self._sleep_until_next_run()

        self.is_running = False
        self.logger.warning("Scheduler stopped")

        # Log scheduler stop
        stop_reason = "disabled_by_user" if not self.settings.get("enabled", True) else (
            "max_runs_reached" if max_runs > 0 and self.run_count >= max_runs else
            "signal_received" if self.should_stop else "unknown"
        )
        log_scheduler_event(
            EventType.SCHEDULER_STOPPED,
            f"Scheduler stopped. Reason: {stop_reason}",
            username=self.username,
            user_id=self.user_id,
            run_count=self.run_count,
            extra_data={
                "stop_reason": stop_reason,
                "total_runs": self.run_count,
                "was_forced": self.should_stop
            }
        )

    def _sleep_until_next_run(self):
        """Wait until next run with should_stop check"""
        if not self.next_run_time:
            return

        while get_moscow_time() < self.next_run_time and not self.should_stop:
            time.sleep(1)


def main():
    """Entry point"""
    print("=" * 60)
    print("VK Ads Manager Scheduler")
    print("   PostgreSQL version")
    print("=" * 60)

    # Initialize DB
    try:
        init_db()
    except Exception as e:
        print(f"DB connection error: {e}")
        sys.exit(1)

    # Run scheduler
    scheduler = VKAdsScheduler()

    try:
        scheduler.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
