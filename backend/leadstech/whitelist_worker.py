import asyncio
import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database import SessionLocal, init_db
from database import crud
from utils.vk_api import (
    toggle_banner_status,
    get_banner_info,
    get_ad_group_full,
    get_campaign_full,
    toggle_ad_group_status,
    toggle_campaign_status
)
from utils.logging_setup import get_logger, setup_logging

# Setup logging
setup_logging()
logger = get_logger(service="leadstech", function="whitelist")

async def whitelist_profitable_banners(roi_threshold: float, enable_banners: bool = True):
    # Get user_id from environment
    user_id = os.environ.get("VK_ADS_USER_ID")
    if not user_id:
        logger.error("VK_ADS_USER_ID environment variable not set")
        return
    try:
        user_id = int(user_id)
    except ValueError:
        logger.error("VK_ADS_USER_ID must be an integer")
        return

    db = SessionLocal()
    try:
        logger.info(f"🚀 Starting whitelist worker for user_id={user_id}. ROI >= {roi_threshold}%, Enable: {enable_banners}")
        
        # Get profitable banners (all, without pagination) for current user
        results, total = crud.get_leadstech_analysis_results(
            db,
            cabinet_name=None,
            limit=10000,
            offset=0,
            user_id=user_id
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
            if not crud.is_whitelisted(db, user_id, banner_id):
                crud.add_to_whitelist(db, user_id, banner_id, note=f"Auto-added: ROI {result.roi_percent:.1f}%")
                added_count += 1
        
        logger.info(f"Added {added_count} banners to whitelist")

        # Enable banners
        if enable_banners:
            cabinets = crud.get_leadstech_cabinets(db, user_id=user_id, enabled_only=True)
            cabinet_tokens = {cab.leadstech_label: cab.account.api_token for cab in cabinets if cab.account}
            
            enabled_count = 0
            failed_count = 0
            
            # Кэши для групп и кампаний, чтобы не делать повторные запросы
            enabled_groups = set()  # ID групп, которые уже активны или были включены
            enabled_campaigns = set()  # ID кампаний, которые уже активны или были включены
            
            # Счетчики для статистики
            campaigns_activated = 0
            groups_activated = 0
            
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
                        base_url = "https://ads.vk.com/api/v2"
                        
                        # Шаг 1: Получаем информацию о баннере
                        banner_info = get_banner_info(api_token, base_url, banner_id)
                        if not banner_info:
                            logger.error(f"❌ Не удалось получить информацию о баннере {banner_id}")
                            failed_count += 1
                            continue
                        
                        ad_group_id = banner_info.get("ad_group_id")
                        if not ad_group_id:
                            logger.error(f"❌ Баннер {banner_id} не содержит ad_group_id")
                            failed_count += 1
                            continue
                        
                        # Шаг 2: Получаем информацию о группе объявлений (только если еще не проверяли)
                        campaign_id = None
                        if ad_group_id not in enabled_groups:
                            group_info = get_ad_group_full(api_token, base_url, ad_group_id)
                            if not group_info:
                                logger.error(f"❌ Не удалось получить информацию о группе {ad_group_id}")
                                failed_count += 1
                                continue
                            
                            group_status = group_info.get("status")
                            campaign_id = group_info.get("ad_plan_id")
                            
                            if not campaign_id:
                                logger.error(f"❌ Группа {ad_group_id} не содержит ad_plan_id (campaign_id)")
                                failed_count += 1
                                continue
                            
                            # Шаг 3: Проверяем кампанию (только если еще не проверяли)
                            if campaign_id not in enabled_campaigns:
                                campaign_info = get_campaign_full(api_token, base_url, campaign_id)
                                if not campaign_info:
                                    logger.error(f"❌ Не удалось получить информацию о кампании {campaign_id}")
                                    failed_count += 1
                                    continue
                                
                                campaign_status = campaign_info.get("status")
                                
                                # Шаг 4: Включаем кампанию, если она выключена
                                if campaign_status != "active":
                                    logger.info(f"⚠️ Кампания {campaign_id} выключена (статус: {campaign_status}), включаем...")
                                    campaign_result = toggle_campaign_status(api_token, base_url, campaign_id, "active")
                                    if not campaign_result.get("success"):
                                        logger.error(f"❌ Не удалось включить кампанию {campaign_id}: {campaign_result.get('error')}")
                                        failed_count += 1
                                        continue
                                    logger.info(f"✅ Кампания {campaign_id} включена")
                                    campaigns_activated += 1
                                
                                # Добавляем в кэш
                                enabled_campaigns.add(campaign_id)
                            
                            # Шаг 5: Включаем группу, если она выключена
                            if group_status != "active":
                                logger.info(f"⚠️ Группа {ad_group_id} выключена (статус: {group_status}), включаем...")
                                group_result = toggle_ad_group_status(api_token, base_url, ad_group_id, "active")
                                if not group_result.get("success"):
                                    logger.error(f"❌ Не удалось включить группу {ad_group_id}: {group_result.get('error')}")
                                    failed_count += 1
                                    continue
                                logger.info(f"✅ Группа {ad_group_id} включена")
                                groups_activated += 1
                            
                            # Добавляем в кэш
                            enabled_groups.add(ad_group_id)
                        
                        # Шаг 6: Включаем баннер
                        vk_result = toggle_banner_status(
                            token=api_token,
                            base_url=base_url,
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
            
            logger.info(f"🏁 Finished. Banners enabled: {enabled_count}, Failed: {failed_count}")
            logger.info(f"📊 Statistics: Campaigns activated: {campaigns_activated}, Groups activated: {groups_activated}")

    except Exception as e:
        logger.error(f"❌ Worker failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--roi", type=float, required=True)
    parser.add_argument("--enable", type=str, default="true")
    
    args = parser.parse_args()
    
    enable_banners = args.enable.lower() == "true"
    
    asyncio.run(whitelist_profitable_banners(args.roi, enable_banners))
