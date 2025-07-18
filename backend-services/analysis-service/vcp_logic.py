import numpy as np
from typing import List, Any

# For VCP screening: the maximum allowable percentage for a pivot's contraction depth.
PIVOT_PRICE_PERC = 0.2


def is_pivot_good(vcp_results: List[Any], current_price: float) -> bool:
    """Checks if the stock is near a valid VCP pivot point.

    A good pivot is characterized by two conditions:
    1. The most recent contraction's depth is within the acceptable
       percentage defined by `PIVOT_PRICE_PERC`.
    2. The current price is trading above the low of the last contraction.

    Args:
        vcp_results: A list of VCP contraction results. Each result is
                     expected to be a list or tuple where index 1 is the
                     high price and index 3 is the low price of the
                     contraction.
        current_price: The current trading price of the stock.

    Returns:
        True if the pivot is considered good, False otherwise.
    """
    if not vcp_results:
        return False

    last_high_price = vcp_results[-1][1]
    last_low_price = vcp_results[-1][3]

    # Avoid division by zero if the high price is zero
    if last_high_price == 0:
        return False

    last_contraction_depth = (last_high_price - last_low_price) / last_high_price

    return last_contraction_depth <= PIVOT_PRICE_PERC and current_price > last_low_price
# For VCP screening: the maximum allowable percentage for the entire correction from the first high.
MAX_CORRECTION_PERC = 0.5


def is_correction_deep(vcp_results: List[tuple[Any, float, Any, float]]) -> bool:
    """Checks if the overall VCP correction is too deep.

    This function determines if the correction from the first high point to the
    deepest subsequent low exceeds the maximum allowable percentage defined by
    `MAX_CORRECTION_PERC`. A deep correction might indicate that the stock is
    in a bear market or has fundamental issues, making it a riskier VCP candidate.

    Args:
        vcp_results: A list of VCP contraction tuples. Each tuple is expected
                     to contain (start_date, high_price, end_date, low_price).

    Returns:
        True if the correction depth is greater than or equal to
        `MAX_CORRECTION_PERC`, indicating a deep correction. False otherwise.
    """
    if not vcp_results:
        return False

    first_high = vcp_results[0][1]
    if first_high == 0:
        return True  # Treat as a deep correction if the high is 0 to avoid division by zero.

    deepest_low = min(low_price for _, _, _, low_price in vcp_results)
    max_correction = (first_high - deepest_low) / first_high

    return max_correction >= MAX_CORRECTION_PERC
def _calculate_volume_trend(volume_list: List[float]) -> tuple[float, float]:
    """Calculates the trend of a volume list using linear regression.

    This helper function performs a linear regression on the provided list of
    volume data to determine its trend, represented by the slope of the
    best-fit line.

    Args:
        volume_list: A list of volume figures (integers or floats).

    Returns:
        A tuple containing the slope and intercept of the linear regression.
        Returns (0.0, 0.0) if the list has fewer than two data points, as a
        trend cannot be determined.
    """
    if not volume_list or len(volume_list) < 2:
        return 0.0, 0.0

    x = np.arange(len(volume_list))
    y = np.array(volume_list)
    slope, intercept = np.polyfit(x, y, 1)
    return slope, intercept


def is_demand_dry(
    vcp_results: List[tuple[int, Any, int, Any]],
    prices: List[float],
    volumes: List[float],
) -> bool:
    """Checks if demand dried up during the last price contraction.

    A "dry up" in demand is a bullish indicator, suggesting that selling
    pressure has subsided. This is determined by two conditions:
    1. The overall volume trend during the last contraction is negative (declining).
    2. There is no recent, significant selling pressure (i.e., volume
       increasing as prices fall in the last few days of the contraction).

    Args:
        vcp_results: A list of VCP contraction tuples. Each tuple is expected
                     to contain (start_index, high_price, end_index, low_price).
        prices: A list of historical prices for the stock.
        volumes: A list of historical volumes for the stock, corresponding
                 to the prices.

    Returns:
        True if demand is considered to have dried up, False otherwise.
    """
    if not vcp_results or not volumes or len(volumes) < 2:
        return False

    last_high_idx, _, last_low_idx, _ = vcp_results[-1]

    if last_high_idx >= len(volumes) or last_low_idx >= len(volumes):
        return False

    contraction_volumes = volumes[last_high_idx : last_low_idx + 1]

    if len(contraction_volumes) < 2:
        return False

    # Check 1: Overall trend should be down
    overall_slope, _ = _calculate_volume_trend(contraction_volumes)
    if overall_slope > 0:
        return False

    # Check 2: No recent selling pressure (volume rising as price falls)
    # Look at the last 3 days of the contraction
    if len(contraction_volumes) > 3:
        recent_prices = prices[last_low_idx - 2 : last_low_idx + 1]
        recent_volumes = contraction_volumes[-3:]

        # If price is falling and volume is rising in the last 3 days, it's a bad sign
        price_is_falling = recent_prices[-1] < recent_prices[0]
        volume_is_rising = recent_volumes[-1] > recent_volumes[0]

        if price_is_falling and volume_is_rising:
            return False

    return True