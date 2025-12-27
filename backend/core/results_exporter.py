"""
Core results exporter - Save analysis results to JSON files
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from utils.logging_setup import get_logger

logger = get_logger(service="vk_api", function="exporter")


def format_summary(
    results: List[Dict],
    spent_limit_rub: float,
    total_accounts: int
) -> Dict:
    """
    Format analysis results into summary dictionary.

    Args:
        results: List of account analysis results
        spent_limit_rub: Default spend limit
        total_accounts: Total number of accounts

    Returns:
        Summary dictionary
    """
    if not results:
        return {
            "analysis_date": datetime.now().isoformat(),
            "period": "N/A",
            "spent_limit_rub_default": spent_limit_rub,
            "total_accounts": total_accounts,
            "summary": {
                "total_unprofitable_banners": 0,
                "total_effective_banners": 0,
                "total_testing_banners": 0,
                "total_spent": 0,
                "total_vk_goals": 0,
                "avg_cost_per_goal": 0,
            },
            "accounts": {},
        }

    # Calculate totals
    total_unprofitable = sum(len(r.get("over_limit", [])) for r in results if r)
    total_effective = sum(len(r.get("under_limit", [])) for r in results if r)
    total_testing = sum(len(r.get("no_activity", [])) for r in results if r)
    total_spent = sum(r.get("total_spent", 0) for r in results if r)
    total_goals = sum(r.get("total_vk_goals", 0) for r in results if r)

    # Get period from first result
    first_result = next((r for r in results if r), None)
    period = "N/A"
    if first_result:
        date_from = first_result.get("date_from", "N/A")
        date_to = first_result.get("date_to", "N/A")
        period = f"{date_from} to {date_to}"

    summary = {
        "analysis_date": datetime.now().isoformat(),
        "period": period,
        "spent_limit_rub_default": spent_limit_rub,
        "total_accounts": total_accounts,
        "summary": {
            "total_unprofitable_banners": total_unprofitable,
            "total_effective_banners": total_effective,
            "total_testing_banners": total_testing,
            "total_spent": total_spent,
            "total_vk_goals": int(total_goals),
            "avg_cost_per_goal": total_spent / total_goals if total_goals > 0 else 0,
        },
        "accounts": {},
    }

    # Add per-account stats
    for result in results:
        if not result:
            continue
        account_name = result["account_name"]
        summary["accounts"][account_name] = {
            "unprofitable_banners": len(result.get("over_limit", [])),
            "effective_banners": len(result.get("under_limit", [])),
            "testing_banners": len(result.get("no_activity", [])),
            "spent": result.get("total_spent", 0.0),
            "vk_goals": int(result.get("total_vk_goals", 0)),
            "spent_limit_rub": result.get("spent_limit", spent_limit_rub),
        }

    return summary


def collect_unprofitable_banners(results: List[Dict]) -> List[Dict]:
    """
    Collect all unprofitable banners from results.

    Args:
        results: List of account analysis results

    Returns:
        List of all unprofitable banner dicts
    """
    all_unprofitable = []
    for result in results:
        if result:
            all_unprofitable.extend(result.get("over_limit", []))
    return all_unprofitable


def save_analysis_results(
    results: List[Dict],
    output_dir: Path,
    spent_limit_rub: float = 100.0,
    total_accounts: int = 0
) -> Tuple[Path, Path]:
    """
    Save analysis results to JSON files.

    Args:
        results: List of account analysis results
        output_dir: Directory to save files
        spent_limit_rub: Default spend limit for summary
        total_accounts: Total number of accounts

    Returns:
        Tuple of (summary_path, unprofitable_path)
    """
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "vk_summary_analysis.json"
    unprofitable_path = output_dir / "vk_all_unprofitable_banners.json"

    # Format summary
    summary = format_summary(results, spent_limit_rub, total_accounts)

    # Collect unprofitable banners
    all_unprofitable = collect_unprofitable_banners(results)

    # Save summary
    try:
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        logger.info(f"Analysis summary saved to {summary_path}")
    except Exception as e:
        logger.error(f"Error saving summary: {e}")

    # Save unprofitable banners
    try:
        with open(unprofitable_path, "w", encoding="utf-8") as f:
            json.dump(all_unprofitable, f, ensure_ascii=False, indent=2)
        logger.info(f"Unprofitable banners saved to {unprofitable_path}")
    except Exception as e:
        logger.error(f"Error saving unprofitable list: {e}")

    return summary_path, unprofitable_path


def get_results_totals(results: List[Dict]) -> Dict:
    """
    Calculate totals from analysis results.

    Args:
        results: List of account analysis results

    Returns:
        Dict with total counts and sums
    """
    totals = {
        "unprofitable": 0,
        "effective": 0,
        "testing": 0,
        "spent": 0.0,
        "goals": 0,
        "accounts_processed": 0,
    }

    for result in results:
        if not result:
            continue
        totals["accounts_processed"] += 1
        totals["unprofitable"] += len(result.get("over_limit", []))
        totals["effective"] += len(result.get("under_limit", []))
        totals["testing"] += len(result.get("no_activity", []))
        totals["spent"] += result.get("total_spent", 0.0)
        totals["goals"] += result.get("total_vk_goals", 0)

    return totals
