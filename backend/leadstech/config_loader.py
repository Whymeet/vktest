"""
LeadsTech Analysis Configuration Loader

Loads configuration from database for LeadsTech analysis.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from database import crud
from utils.time_utils import get_moscow_time
from utils.logging_setup import get_logger

from leadstech.leadstech_client import LeadstechClientConfig

logger = get_logger(service="leadstech", function="config")


@dataclass
class CabinetConfig:
    """Configuration for a single LeadsTech cabinet."""
    id: int
    account_id: int
    account_name: str
    api_token: str
    leadstech_label: str
    enabled: bool


@dataclass
class LeadstechAnalysisConfig:
    """Complete configuration for LeadsTech analysis."""
    leadstech: LeadstechClientConfig
    cabinets: List[CabinetConfig]
    date_from: date
    date_to: date
    banner_sub_fields: List[str]
    user_id: int


def get_user_id_from_env() -> int:
    """
    Get user ID from environment variable.

    Returns:
        User ID as integer

    Raises:
        ValueError: If VK_ADS_USER_ID is not set or not a valid integer
    """
    user_id_str = os.environ.get("VK_ADS_USER_ID")
    if not user_id_str:
        raise ValueError("VK_ADS_USER_ID environment variable not set")

    try:
        return int(user_id_str)
    except ValueError:
        raise ValueError("VK_ADS_USER_ID must be an integer")


def parse_banner_sub_fields(raw_value: Optional[str | List[str]]) -> List[str]:
    """
    Parse banner_sub_fields from database value.

    Handles backwards compatibility where value might be:
    - None -> ["sub4"]
    - str (JSON) -> parsed list
    - str (single value) -> [value]
    - List -> returned as-is

    Args:
        raw_value: Raw value from database

    Returns:
        List of sub field names
    """
    if raw_value is None:
        return ["sub4"]

    if isinstance(raw_value, list):
        return raw_value

    if isinstance(raw_value, str):
        # Try to parse as JSON
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        # Treat as single value
        return [raw_value]

    return ["sub4"]


def load_cabinets(db: Session, user_id: int) -> List[CabinetConfig]:
    """
    Load enabled LeadsTech cabinets from database.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        List of cabinet configurations
    """
    cabinets = crud.get_leadstech_cabinets(db, user_id=user_id, enabled_only=True)
    result: List[CabinetConfig] = []

    for cab in cabinets:
        if not cab.account:
            logger.warning(f"Cabinet {cab.id} has no linked account, skipping")
            continue

        result.append(CabinetConfig(
            id=cab.id,
            account_id=cab.account_id,
            account_name=cab.account.name,
            api_token=cab.account.api_token,
            leadstech_label=cab.leadstech_label,
            enabled=cab.enabled,
        ))

    return result


def load_analysis_config(db: Session, user_id: int) -> LeadstechAnalysisConfig:
    """
    Load complete analysis configuration from database.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        Complete analysis configuration

    Raises:
        ValueError: If LeadsTech is not configured or no cabinets found
    """
    logger.info(f"Loading LeadsTech config for user_id={user_id}")

    # Get LeadsTech config
    lt_config = crud.get_leadstech_config(db, user_id=user_id)
    if not lt_config:
        raise ValueError(f"LeadsTech not configured for user {user_id}")

    # Get enabled cabinets
    cabinets = load_cabinets(db, user_id)
    if not cabinets:
        raise ValueError(f"No enabled LeadsTech cabinets for user {user_id}")

    logger.info(f"Found {len(cabinets)} enabled cabinet(s)")
    for cab in cabinets:
        logger.info(
            f"  - Cabinet ID {cab.id}: account_id={cab.account_id}, "
            f"label='{cab.leadstech_label}', enabled={cab.enabled}"
        )

    # Calculate date range
    today = get_moscow_time().date()
    if lt_config.date_from and lt_config.date_to:
        date_from = datetime.strptime(lt_config.date_from, "%Y-%m-%d").date()
        date_to = datetime.strptime(lt_config.date_to, "%Y-%m-%d").date()
    else:
        # Default to last 10 days if no dates configured
        date_to = today
        date_from = date_to - timedelta(days=10)

    logger.info(f"Analysis period: {date_from} to {date_to}")

    # Parse banner sub fields
    banner_sub_fields = parse_banner_sub_fields(lt_config.banner_sub_fields)
    logger.info(f"Analyzing sub fields: {banner_sub_fields}")

    # Create LeadsTech client config
    leadstech_client_cfg = LeadstechClientConfig(
        base_url=(lt_config.base_url.strip() if lt_config.base_url else "https://api.leads.tech"),
        login=(lt_config.login.strip() if lt_config.login else ""),
        password=(lt_config.password.strip() if lt_config.password else ""),
        banner_sub_fields=banner_sub_fields,
    )

    return LeadstechAnalysisConfig(
        leadstech=leadstech_client_cfg,
        cabinets=cabinets,
        date_from=date_from,
        date_to=date_to,
        banner_sub_fields=banner_sub_fields,
        user_id=user_id,
    )
