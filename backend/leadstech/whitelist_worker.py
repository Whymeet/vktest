import asyncio
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database import SessionLocal, init_db
from database import crud
from utils.vk_api import toggle_banner_status

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("whitelist_worker")

async def whitelist_profitable_banners(roi_threshold: float, analysis_id: str = None, enable_banners: bool = True):
    db = SessionLocal()
    try:
        logger.info(f"🚀 Starting whitelist worker. ROI >= {roi_threshold}%, Enable: {enable_banners}")
        
        # Get profitable banners
        results = crud.get_leadstech_analysis_results(
            db,
            analysis_id=analysis_id,
            cabinet_name=None,
            limit=10000
        )

        profitable = [
            r for r in results 
            if r.roi_percent is not None and r.roi_percent >= roi_threshold
        ]

        if not profitable:
            logger.info(f"⚠️ No banners found with ROI >= {roi_threshold}%")
            return

        logger.info(f"Found {len(profitable)} profitable banners")

        # Add to whitelist
        added_count = 0
        for result in profitable:
            banner_id = result.banner_id
            if not crud.is_whitelisted(db, banner_id):
                crud.add_to_whitelist(db, banner_id, note=f"Auto-added: ROI {result.roi_percent:.1f}%")
                added_count += 1
        
        logger.info(f"Added {added_count} banners to whitelist")

        # Enable banners
        if enable_banners:
            cabinets = crud.get_leadstech_cabinets(db, enabled_only=True)
            cabinet_tokens = {cab.leadstech_label: cab.account.api_token for cab in cabinets if cab.account}
            
            enabled_count = 0
            failed_count = 0
            
            # Process in batches of 30 (VK API limit: 30 requests/second)
            BATCH_SIZE = 30
            total_banners = len(profitable)
            
            for batch_start in range(0, total_banners, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, total_banners)
                batch = profitable[batch_start:batch_end]
                
                logger.info(f"📦 Processing batch {batch_start // BATCH_SIZE + 1}: banners {batch_start + 1}-{batch_end} of {total_banners}")
                
                for result in batch:
                    banner_id = result.banner_id
                    cabinet_label = result.leadstech_label
                    
                    api_token = cabinet_tokens.get(cabinet_label)
                    if not api_token:
                        logger.error(f"❌ No API token for cabinet {cabinet_label} (Banner {banner_id})")
                        failed_count += 1
                        continue

                    try:
                        vk_result = toggle_banner_status(
                            token=api_token,
                            base_url="https://ads.vk.com/api/v2",
                            banner_id=banner_id,
                            status="active"
                        )
                        
                        if vk_result.get("success"):
                            enabled_count += 1
                            logger.info(f"✅ Enabled banner {banner_id} (ROI {result.roi_percent:.1f}%)")
                        else:
                            failed_count += 1
                            logger.error(f"❌ Failed to enable {banner_id}: {vk_result.get('error')}")
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"❌ Exception enabling {banner_id}: {e}")
                
                # Wait 0.5 seconds between batches to respect VK API rate limit
                if batch_end < total_banners:
                    logger.info(f"⏳ Waiting 0.5s before next batch...")
                    await asyncio.sleep(0.5)
            
            logger.info(f"🏁 Finished. Enabled: {enabled_count}, Failed: {failed_count}")

    except Exception as e:
        logger.error(f"❌ Worker failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--roi", type=float, required=True)
    parser.add_argument("--analysis_id", type=str, default=None)
    parser.add_argument("--enable", type=str, default="true")
    
    args = parser.parse_args()
    
    enable_banners = args.enable.lower() == "true"
    
    asyncio.run(whitelist_profitable_banners(args.roi, args.analysis_id, enable_banners))
