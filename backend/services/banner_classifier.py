"""
Banner Classifier Service
Classifies banners as positive/negative based on scaling conditions.
Uses the same condition logic as check_group_conditions in crud/scaling.py
"""
from typing import List, Dict, Set, Tuple, Optional, Callable
from dataclasses import dataclass
from utils.logging_setup import get_logger

logger = get_logger(service="banner_classifier")


@dataclass
class ClassificationResult:
    """Result of banner classification for a group"""
    group_id: int
    group_name: str
    positive_banner_ids: List[int]
    negative_banner_ids: List[int]
    has_positive: bool  # True if at least one positive banner

    @property
    def total_banners(self) -> int:
        return len(self.positive_banner_ids) + len(self.negative_banner_ids)


def check_banner_conditions(stats: dict, conditions: List[dict], verbose: bool = False) -> bool:
    """
    Check if banner stats match ALL conditions (AND logic).
    Same logic as check_group_conditions in crud/scaling.py

    Args:
        stats: Dict with keys: spent, shows, clicks, goals, cost_per_goal, ctr, cpc, roi
        conditions: List of dicts with keys: metric, operator, value
        verbose: Enable detailed logging

    Returns:
        True if ALL conditions are satisfied (banner is positive)
    """
    def log(msg):
        if verbose:
            logger.debug(msg)

    if not conditions:
        log("No conditions - returning False")
        return False  # No conditions = don't match anything

    for idx, condition in enumerate(conditions):
        metric = condition.get("metric", "")
        operator = condition.get("operator", ">")
        threshold = float(condition.get("value", 0))

        # Get metric value from stats
        actual_value = stats.get(metric)
        log(f"[{idx+1}] Checking: {metric} {operator} {threshold} (raw value: {actual_value})")

        # Handle None and special cases
        if actual_value is None:
            if metric == "cost_per_goal":
                # If no goals, cost_per_goal is infinite
                goals = stats.get("goals", 0) or stats.get("vk_goals", 0)
                if goals == 0:
                    actual_value = float('inf')
                else:
                    spent = stats.get("spent", 0) or 0
                    actual_value = spent / goals if goals > 0 else float('inf')
            elif metric == "ctr":
                shows = stats.get("shows", 0) or 0
                clicks = stats.get("clicks", 0) or 0
                actual_value = (clicks / shows * 100) if shows > 0 else 0
            elif metric == "cpc":
                clicks = stats.get("clicks", 0) or 0
                spent = stats.get("spent", 0) or 0
                actual_value = (spent / clicks) if clicks > 0 else float('inf')
            elif metric == "roi":
                # ROI from LeadsTech - None means no data available
                log(f"ROI not available for this banner")
                return False  # Skip banner if no ROI data when ROI condition is used
            else:
                actual_value = 0

        # Normalize goals field name
        if metric == "goals" and actual_value == 0:
            vk_goals = stats.get("vk_goals", 0) or 0
            if vk_goals > 0:
                actual_value = vk_goals

        # Check condition based on operator
        condition_met = False

        # Special handling for infinite cost_per_goal
        if metric == "cost_per_goal" and actual_value == float('inf'):
            if operator in ("not_equals", "!="):
                condition_met = True
            else:
                condition_met = False
        elif operator in ("equals", "=", "=="):
            condition_met = (actual_value == threshold)
        elif operator in ("not_equals", "!=", "<>"):
            condition_met = (actual_value != threshold)
        elif operator in ("greater_than", ">"):
            condition_met = (actual_value > threshold)
        elif operator in ("less_than", "<"):
            condition_met = (actual_value < threshold)
        elif operator in ("greater_or_equal", ">="):
            condition_met = (actual_value >= threshold)
        elif operator in ("less_or_equal", "<="):
            condition_met = (actual_value <= threshold)
        else:
            # Unknown operator - FAIL the condition
            condition_met = False
            log(f"Unknown operator: {operator}")

        if not condition_met:
            log(f"Condition NOT met: {actual_value} {operator} {threshold}")
            return False

        log(f"Condition met: {actual_value} {operator} {threshold}")

    log("ALL conditions met - banner is POSITIVE")
    return True


def create_conditions_checker(conditions: List[dict]) -> Callable[[dict], bool]:
    """
    Create a conditions checker function for use with streaming classification.

    Args:
        conditions: List of condition dicts

    Returns:
        Function that takes stats dict and returns True if positive
    """
    def checker(stats: dict) -> bool:
        return check_banner_conditions(stats, conditions, verbose=False)

    return checker


class BannerClassifier:
    """
    Classifies banners based on conditions.
    Uses AND logic - banner must match ALL conditions to be positive.
    """

    def __init__(self, conditions: List[dict]):
        """
        Args:
            conditions: List of {metric, operator, value}
        """
        self.conditions = conditions
        self._check_fn = create_conditions_checker(conditions)

    def classify_banner(self, stats: dict) -> bool:
        """
        Check if banner matches ALL conditions.

        Args:
            stats: Banner statistics dict

        Returns:
            True if banner is positive (matches all conditions)
        """
        return self._check_fn(stats)

    def classify_all(
        self,
        banners_with_stats: Dict[int, dict],  # banner_id -> stats
        banner_to_group: Dict[int, int],      # banner_id -> group_id
        groups_info: Optional[Dict[int, str]] = None  # group_id -> group_name
    ) -> Dict[int, ClassificationResult]:
        """
        Classify all banners and group by ad_group_id.

        Args:
            banners_with_stats: Dict mapping banner_id to stats dict
            banner_to_group: Dict mapping banner_id to group_id
            groups_info: Optional dict mapping group_id to group_name

        Returns:
            Dict mapping group_id to ClassificationResult
        """
        if groups_info is None:
            groups_info = {}

        # Initialize results by group
        results: Dict[int, ClassificationResult] = {}

        for banner_id, stats in banners_with_stats.items():
            group_id = banner_to_group.get(banner_id)
            if group_id is None:
                continue

            # Initialize group result if needed
            if group_id not in results:
                results[group_id] = ClassificationResult(
                    group_id=group_id,
                    group_name=groups_info.get(group_id, f"Group {group_id}"),
                    positive_banner_ids=[],
                    negative_banner_ids=[],
                    has_positive=False
                )

            # Classify banner
            is_positive = self.classify_banner(stats)

            if is_positive:
                results[group_id].positive_banner_ids.append(banner_id)
                results[group_id].has_positive = True
            else:
                results[group_id].negative_banner_ids.append(banner_id)

        return results

    def get_groups_to_duplicate(
        self,
        classification_results: Dict[int, ClassificationResult]
    ) -> List[int]:
        """
        Get list of group_ids that have at least one positive banner.

        Args:
            classification_results: Dict from classify_all()

        Returns:
            List of group IDs to duplicate
        """
        return [
            group_id
            for group_id, result in classification_results.items()
            if result.has_positive
        ]


def classify_banners_in_memory(
    banners_with_stats: Dict[int, dict],
    banner_to_group: Dict[int, int],
    conditions: List[dict],
    groups_info: Optional[Dict[int, str]] = None
) -> Tuple[Set[int], Set[int], Dict[int, ClassificationResult]]:
    """
    Convenience function to classify banners in memory.

    Args:
        banners_with_stats: Dict mapping banner_id to stats
        banner_to_group: Dict mapping banner_id to group_id
        conditions: List of condition dicts
        groups_info: Optional dict mapping group_id to name

    Returns:
        Tuple of (positive_ids, negative_ids, group_results)
    """
    classifier = BannerClassifier(conditions)
    group_results = classifier.classify_all(banners_with_stats, banner_to_group, groups_info)

    positive_ids: Set[int] = set()
    negative_ids: Set[int] = set()

    for result in group_results.values():
        positive_ids.update(result.positive_banner_ids)
        negative_ids.update(result.negative_banner_ids)

    return positive_ids, negative_ids, group_results


def get_classification_summary(
    positive_ids: Set[int],
    negative_ids: Set[int],
    banner_to_group: Dict[int, int]
) -> dict:
    """
    Get summary statistics for classification.

    Returns:
        Dict with counts and percentages
    """
    total = len(positive_ids) + len(negative_ids)
    groups_with_positive = set()

    for banner_id in positive_ids:
        group_id = banner_to_group.get(banner_id)
        if group_id:
            groups_with_positive.add(group_id)

    return {
        "total_banners": total,
        "positive_banners": len(positive_ids),
        "negative_banners": len(negative_ids),
        "positive_percent": (len(positive_ids) / total * 100) if total > 0 else 0,
        "groups_to_duplicate": len(groups_with_positive),
        "total_groups": len(set(banner_to_group.values()))
    }
