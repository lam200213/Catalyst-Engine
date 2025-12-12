# backend-services/analysis-service/vcp_logic.py
import numpy as np
from typing import List, Any

# --- Constants ---
# For VCP detection: number of consecutive windows without a new high/low to define a peak/trough.
COUNTER_THRESHOLD = 5
# For VCP screening: the maximum allowable percentage for a pivot's contraction depth.
PIVOT_PRICE_PERC = 0.2
# Max trading days since the pivot low for it to be considered "fresh".
PIVOT_FRESHNESS_DAYS = 20
# Price level above the pivot high that suggests a breakout has already occurred.
PIVOT_BREAKOUT_THRESHOLD = 1.05  # 5%
# For VCP screening: the maximum allowable percentage for the entire correction from the first high.
MAX_CORRECTION_PERC = 0.5
# For VCP screening: the maximum allowable contraction for the entire sequence.
MAX_CONTRACTION = 8
# Tolerance for how much a newer low can undercut an older low (3% shakeout).
LOW_SHAKEOUT_TOLERANCE = 0.03
# Tolerance for how much a newer contraction high can exceed an older high
# and still be considered part of the same VCP base.
HIGH_CONTAINMENT_TOLERANCE = 0.04
# Flat Base Constants
FLAT_BASE_MAX_DEPTH = 0.15 # 15% max depth for a flat base
FLAT_BASE_MIN_WEEKS = 4    # Minimum 4 weeks (20 trading days) duration

# --- Pullback (PB) Setup Constants ---
PB_ZONE_LOWER = 0.02  # Must be at least 2% above pivot (confirmed breakout)
PB_ZONE_UPPER = 0.15  # Must be less than 15% above pivot (not extended/climax)
PB_DISTRIBUTION_LOOKBACK = 10 # Check last 10 days for distribution
PB_DISTRIBUTION_VOL_THRESHOLD = 2.0 # Down days with >2x avg volume are red flags
PB_MAX_PATTERN_AGE_DAYS = 60 # Pattern shouldn't be ancient (approx 3 months post-pivot is max for a PB entry)

# --- VCP (Volatility Contraction Pattern) Logic ---

# --- VCP Pattern Detection ---
def find_one_contraction(prices, start_index):
    """
    Finds a single volatility contraction pattern (VCP) from a given start index.
    It searches for a local high (peak) followed by a local low (trough).
    A peak/trough is identified when a new high/low is not found for `COUNTER_THRESHOLD` consecutive 5-day windows.
    
    Returns:
        tuple: (high_idx, high_price, low_idx, low_price) or None if no contraction is found.
    """
    if start_index < 0 or start_index >= len(prices):
        return None

    # --- Find Local High (Peak) ---
    local_highest_price = -float('inf')
    local_highest_idx = -1
    no_new_high_count = 0

    # Iterate from start_index to find a peak
    for i in range(start_index, len(prices)):
        window_end = min(i + 5, len(prices))
        if i >= window_end: break

        window_prices = prices[i : window_end]
        if not window_prices: continue

        current_window_high = max(window_prices)
        current_window_high_relative_idx = window_prices.index(current_window_high)
        current_window_high_global_idx = i + current_window_high_relative_idx

        if current_window_high > local_highest_price:
            local_highest_price = current_window_high
            local_highest_idx = current_window_high_global_idx
            no_new_high_count = 0
        else:
            no_new_high_count += 1
        
        if no_new_high_count >= COUNTER_THRESHOLD:
            break
    
    if no_new_high_count < COUNTER_THRESHOLD or local_highest_idx == -1:
        return None

    # --- Find Local Low (Trough) ---
    local_lowest_price = float('inf')
    local_lowest_idx = -1
    no_new_low_count = 0

    # Iterate from the local_highest_idx to find a trough
    for j in range(local_highest_idx, len(prices)):
        window_end = min(j + 5, len(prices))
        if j >= window_end: break

        window_prices = prices[j : window_end]
        if not window_prices: continue

        current_window_low = min(window_prices)
        current_window_low_relative_idx = window_prices.index(current_window_low)
        current_window_low_global_idx = j + current_window_low_relative_idx

        if current_window_low < local_lowest_price:
            local_lowest_price = current_window_low
            local_lowest_idx = current_window_low_global_idx
            no_new_low_count = 0
        else:
            no_new_low_count += 1
        
        if no_new_low_count >= COUNTER_THRESHOLD:
            break
    
    if no_new_low_count < COUNTER_THRESHOLD or local_lowest_idx == -1:
        return None

    if local_highest_idx >= local_lowest_idx or local_highest_price == local_lowest_price:
        return None

    return (local_highest_idx, local_highest_price, local_lowest_idx, local_lowest_price)

def find_volatility_contraction_pattern(prices):
    """
    Main function to detect VCPs by iteratively calling find_one_contraction.
    Collects all detected contractions to form the complete pattern.
    """
    contractions = []
    start_index = 0
    while start_index < len(prices):
        result = find_one_contraction(prices, start_index)
        if result:
            contractions.append(result)
            # Advance start_index past the found contraction's low point to search for the next one.
            start_index = result[2] + 1
        else:
            # If no more contractions are found, advance by one to avoid an infinite loop.
            start_index += 1
    return contractions

def _filter_vcp_contractions(vcp_results: List[tuple]) -> List[tuple]:
    """
    Filters the raw detected contractions to isolate the valid VCP sequence.
    This logic "sanitizes" the pattern by:
    1. Capping the sequence to the most recent N contractions.
    2. Resetting if volatility expands (newer contraction > older contraction).
    3. Resetting if the structure breaks (newer low undercuts older low).
    4. Resetting on a deep base (start of a new base).
    
    Args:
        vcp_results: List of (high_idx, high_price, low_idx, low_price)
        
    Returns:
        A subset of vcp_results representing the valid, current base.
    """
    if not vcp_results: 
        return []
    
    # 1. Cap count to reduce noise (most VCPs are 2T-4T, rarely >6T)
    # We work backwards from the pivot (the last result)
    candidates = vcp_results[-MAX_CONTRACTION:] 
    
    if not candidates: 
        return []

    # Start with the most recent contraction (the Pivot)
    filtered = [candidates[-1]] 
    
    # Iterate backwards from second-to-last
    for i in range(len(candidates) - 2, -1, -1):
        prev = filtered[0]  # newer contraction (to the right)
        curr = candidates[i]  # older contraction (to the left)

        prev_depth = (prev[1] - prev[3]) / prev[1] if prev[1] else 0
        curr_depth = (curr[1] - curr[3]) / curr[1] if curr[1] else 0

        # Rule A: Volatility Contraction (Shrinkage)
        if prev_depth > (curr_depth * 1.2) and prev_depth > 0.05:
            break

        # Rule B: Structural Integrity (Higher Lows)
        prev_low = prev[3]
        curr_low = curr[3]
        if prev_low < curr_low * (1 - LOW_SHAKEOUT_TOLERANCE):
            # Newer low is more than 3% below the older low -> broken structure.
            break

        # Rule C: High Containment (No big stair-step up)
        prev_high = prev[1]
        curr_high = curr[1]
        # If the newer high is more than 3% above the older high,
        # treat this as a new leg, not part of the same base.
        if prev_high > curr_high * (1 + HIGH_CONTAINMENT_TOLERANCE):
            break

        # Rule D: Deep Base Reset
        # If the older contraction is very deep (>45%), it likely marks the 
        # start of the entire base (the "L" in the "W"). Include it, then stop.
        filtered.insert(0, curr)
        if curr_depth > (MAX_CORRECTION_PERC-0.05): # Close to MAX_CORRECTION_PERC
            break
            
    return filtered

def _check_flat_base_fallback(prices: list[float]) -> list[tuple] | None:
    """
    Detects if the recent price action constitutes a 'Flat Base'.
    Defined as:
    1. Duration >= 4 weeks (20 days).
    2. Total depth (Highest High to Lowest Low) <= 15%.
    
    If detected, returns a synthetic 'contraction' tuple representing the base:
    [(start_idx, max_high, end_idx, min_low)]
    This allows the rest of the pipeline to treat it as a valid, albeit flat, pattern.
    """
    min_days = FLAT_BASE_MIN_WEEKS * 5
    if len(prices) < min_days:
        return None
    
    # Look at the most recent window (e.g., last 6 weeks or so, or simply since the last major high)
    # For a simple fallback, let's analyze the last ~30-40 days 
    lookback = min(len(prices), 40) 
    recent_prices = prices[-lookback:]
    
    max_price = max(recent_prices)
    min_price = min(recent_prices)
    max_idx = prices.index(max_price, len(prices) - lookback)
    min_idx = prices.index(min_price, len(prices) - lookback) # roughly find the low
    
    # Ensure High comes before Low is NOT strictly required for a flat base, 
    # but for VCP logic we need a pivot. 
    # In a flat base, the "Pivot" is simply the break of the High.
    # So we structure the tuple as (High_Index, High_Price, Last_Index, Current_Price)
    # effectively treating the entire consolidation as one shallow 'contraction'.
    
    depth = (max_price - min_price) / max_price if max_price > 0 else 0
    
    if depth <= FLAT_BASE_MAX_DEPTH:
        # It's a flat base!
        # Create a synthetic result: 
        # Start: Index of the High
        # End: The very last data point (since we are still IN the base or just breaking out)
        last_idx = len(prices) - 1
        return [(max_idx, max_price, last_idx, prices[last_idx])]
        
    return None

def _compute_vcp_signature(
    prices: list[float],
    vcp_results: list[tuple[int, float, int, float]],
) -> str:
    """
    Computes the compact SEPA-style VCP signature:
        "{BaseLengthWeeks}W-{MaxDepthPct}/{LastDepthPct}-{TCount}T"
    Example: "40W-31/3-4T"
    """
    if not vcp_results or not prices:
        return ""

    # 1) Base duration: First contraction High -> Last contraction Low (Pivot)
    # This prevents "drift" after the pivot from inflating the base duration.
    base_start_idx = int(vcp_results[0][0])
    base_pivot_idx = int(vcp_results[-1][2]) # Use pivot low index, not len(prices)
    
    base_length_days = max(0, base_pivot_idx - base_start_idx)
    base_length_weeks = max(1, round(base_length_days / 5))

    # 2) Depths
    depths = []
    for _, high_price, _, low_price in vcp_results:
        depths.append((high_price - low_price) / high_price if high_price else 0.0)

    max_depth = max(depths) if depths else 0.0
    last_depth = depths[-1] if depths else 0.0

    # 3) Symmetry: number of contractions (T count)
    t_count = len(vcp_results)

    return f"{base_length_weeks}W-{int(max_depth * 100)}/{int(last_depth * 100)}-{t_count}T"

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
    if not vcp_results: return False

    last_high_price = vcp_results[-1][1]
    last_low_price = vcp_results[-1][3]

    if last_high_price == 0: return False

    # 1. Depth Check
    depth = (last_high_price - last_low_price) / last_high_price
    if depth > PIVOT_PRICE_PERC: return False # Too deep

    # 2. Location Check
    # Price must be in the upper 50% of the pivot range to be "Ready"
    # Pivot Range = High - Low
    # Threshold = Low + (Range * 0.5)
    pivot_range = last_high_price - last_low_price
    min_valid_price = last_low_price + (pivot_range * 0.3) # Allow a bit more wiggle room (30%)

    if current_price < min_valid_price:
        return False # Hanging at the lows -> Broken/Weak

    return True

def is_volume_dry_up_at_pivot(
    volumes: list[float],
    pivot_idx: int,
    lookback_days: int = 50,
    pivot_window: int = 3,
) -> tuple[bool, float]:
    """
    Checks if volume dried up at the pivot low compared to the recent 50-day average.

    Returns:
        (is_dry, ratio) where ratio = avg_volume_around_pivot / avg_50d_volume.
        is_dry is True when ratio < 1.0.
    """
    if not volumes or pivot_idx < 0 or pivot_idx >= len(volumes):
        return False, 1.0

    if len(volumes) < lookback_days:
        # Not enough history to make a robust 50D judgment
        return False, 1.0

    start_50 = max(0, pivot_idx - lookback_days + 1)
    vol_slice_50 = volumes[start_50 : pivot_idx + 1]
    if not vol_slice_50:
        return False, 1.0

    vol_50d_avg = float(np.mean(vol_slice_50))
    if vol_50d_avg <= 0.0:
        return False, 1.0

    # Average volume over a small window around the pivot (final contraction)
    start_pivot = max(0, pivot_idx - pivot_window + 1)
    vol_slice_pivot = volumes[start_pivot : pivot_idx + 1]
    vol_pivot_avg = float(np.mean(vol_slice_pivot)) if vol_slice_pivot else vol_50d_avg

    ratio = vol_pivot_avg / vol_50d_avg
    is_dry = ratio < 1.0  # "Below 50D average" baseline requirement

    return is_dry, ratio

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

def get_vcp_footprint(
    vcp_results: list[tuple[int, float, int, float]]
) -> tuple[list[str], str]:
    """
    Calculates the VCP footprint as a human-readable summary of each contraction.

    Returns:
        (footprint_list, footprint_str) where footprint_str is:
            "10D 15.5% | 8D 7.2% | ..."
        The SEPA-style base signature (e.g. "40W-31/3-4T") is composed
        at a higher orchestration layer where price history is available.
    """
    if not vcp_results:
        return [], ""

    footprint_list: list[str] = []
    for high_idx, high_price, low_idx, low_price in vcp_results:
        if high_price:
            contraction_depth = (high_price - low_price) / high_price
        else:
            contraction_depth = 0.0
        contraction_days = low_idx - high_idx
        footprint_list.append(f"{contraction_days}D {contraction_depth:.1%}")

    footprint_str = " | ".join(footprint_list)
    return footprint_list, footprint_str

def check_pullback_setup(
    prices: List[float], 
    volumes: List[float], 
    pivot_price: float, 
    vcp_passed: bool,
    is_pivot_good: bool,
    pattern_age_days: int
) -> bool:
    """
    Determines if a stock is in a valid 'Pullback' (PB) structural setup.
    
    Concept:
    Identifies stocks that have successfully broken out from a valid base and are 
    currently 'resting' or 'holding' in a buyable zone. 
    
    This is a FORWARD-LOOKING flag. It does not necessarily mean the stock is 
    down today. It means: "The structure is strong, the trend is up, and the 
    price is slightly extended but stable. If it dips on low volume, BUY."

    Criteria:
    1. Base Validity: Must have passed VCP and have a 'Good' pivot.
    2. Freshness: The base isn't ancient (e.g., < 60 days since pivot).
    3. Position: Price is > 2% above pivot (breakout real) but < 15% (not climax).
    4. Trend: Price is above a RISING 50-day Moving Average.
    5. Character: No heavy distribution (high vol selling) in the last 10 days.

    Args:
        prices: Historical closing prices.
        volumes: Historical volumes.
        pivot_price: The confirmed pivot point from the VCP analysis.
        vcp_passed: Boolean result of the VCP screening.
        is_pivot_good: Boolean indicating if the pivot point itself was structurally sound.
        pattern_age_days: Days since the pivot low formed.

    Returns:
        True if the stock is a prime candidate for a pullback entry.
    """
    # 1. Base Validity Checks
    if not vcp_passed or not is_pivot_good or not pivot_price or pivot_price <= 0:
        return False
    
    # 2. Freshness Check
    # We allow a wider window than "Pivot Freshness" because a pullback happens 
    # *after* the breakout run-up. 
    if pattern_age_days is None or pattern_age_days > PB_MAX_PATTERN_AGE_DAYS:
        return False

    if not prices or not volumes or len(prices) < 50:
        return False

    current_price = prices[-1]
    
    # 3. Position Check: "Extended but Constructive"
    pct_above_pivot = (current_price - pivot_price) / pivot_price
    
    if not (PB_ZONE_LOWER <= pct_above_pivot <= PB_ZONE_UPPER):
        return False # Too close (failed breakout risk) or too far (extended)

    # 4. Trend Check: Above Rising 50-day MA
    # We need at least 50 days of data.
    ma_50_current = np.mean(prices[-50:])
    
    # Check if price is above MA 50
    if current_price < ma_50_current:
        return False
    
    # Check if MA 50 is rising (compare to MA 50 from 1 day ago)
    # MA 50 yesterday = mean of prices[-51:-1]
    if len(prices) >= 51:
        ma_50_prev = np.mean(prices[-51:-1])
        if ma_50_current < ma_50_prev:
            return False # MA is flattening or rolling over

    # 5. Distribution Check: Character of the "Rest"
    # Ensure we don't see institutional selling (distribution)
    recent_prices = prices[-PB_DISTRIBUTION_LOOKBACK:]
    recent_volumes = volumes[-PB_DISTRIBUTION_LOOKBACK:]
    
    avg_vol_50 = np.mean(volumes[-50:]) # Robust baseline

    distribution_days = 0
    
    # Calculate distribution days in the lookback window
    start_idx = len(prices) - PB_DISTRIBUTION_LOOKBACK
    
    for i in range(PB_DISTRIBUTION_LOOKBACK):
        global_idx = start_idx + i
        if global_idx <= 0: continue
        
        close = prices[global_idx]
        prev_close = prices[global_idx - 1]
        vol = volumes[global_idx]
        
        is_down_day = close < prev_close
        is_heavy_vol = vol > (avg_vol_50 * PB_DISTRIBUTION_VOL_THRESHOLD)
        
        if is_down_day and is_heavy_vol:
            distribution_days += 1

    # Tolerance: Allow max 1 bad day. 2+ implies a trend change.
    if distribution_days > 1:
        return False

    return True

def run_vcp_screening(vcp_results: list[tuple], prices: list[float], volumes: list[float], mode: str = 'full') -> tuple[bool, str, dict]:
    """
    Orchestrates VCP screening checks in one of two modes.

    Applies _filter_vcp_contractions first to "sanitize" the pattern.
    This prevents treating 12-month noisy history as a single 12T pattern.
    Includes FALLBACK logic for 'Flat Bases' if standard VCP detection fails or finds insufficient contractions.
    Args:
        vcp_results: Detected VCP contraction tuples.
        prices: Historical closing prices.
        volumes: Historical volumes.
        mode: 'full' to run all checks, 'fast' to halt on first failure.

    Returns:
        (vcp_pass_status, vcp_footprint_str, details_dict)
        where vcp_footprint_str now includes the SEPA-style signature, e.g.:
            "40W-31/3-4T (13D 5.0% | 10D 6.2% | 8D 6.9% | 6D 5.0%)"
    """
    # 1) Filter raw results to get the valid VCP sequence
    # This trims "49W-19/8-12T" down to the actual constructive base (e.g. "15W-15/5-3T")
    filtered_results = _filter_vcp_contractions(vcp_results)
    
    is_flat_base = False
    
    # --- CHECK 1: Minimum Contractions OR Flat Base Fallback ---
    # A standard VCP pattern requires at least 2 contractions (2T).
    # A single contraction is just a pullback/cup, not a VCP.
    if not filtered_results or len(filtered_results) < 2:
        # Standard VCP failed. Try Flat Base detection.
        flat_base_result = _check_flat_base_fallback(prices)
        
        if flat_base_result:
            # It's a valid Flat Base! Use this synthetic result.
            filtered_results = flat_base_result
            is_flat_base = True
        else:
            return False, "", {"message": "Insufficient contraction count (min 2T) and no Flat Base detected"}

    # 2) Build footprint and signature
    # Note: Flat base signature will look like "XW-5%/5%-1T" which is accurate
    _, raw_footprint_str = get_vcp_footprint(filtered_results)
    signature = _compute_vcp_signature(prices, filtered_results)
    
    footprint_str = f"{signature} ({raw_footprint_str})" if (signature and raw_footprint_str) else (raw_footprint_str or signature)
    
    if is_flat_base:
        footprint_str = f"Flat Base: {footprint_str}"

    # 3) Run logic on the FILTERED results (Pivot is the last one)
    last_high_idx, last_high_price, last_low_idx, _ = filtered_results[-1]

    # Fast mode: short-circuit on first failure (for scheduler-service)
    if mode == "fast":
        if not is_pivot_good(filtered_results, prices[-1]):
            return False, footprint_str, {}
        # Flat base is by definition shallow, so correction check usually passes, 
        # but good to keep the guardrail.
        if is_correction_deep(filtered_results):
            # Deep correction is a failure condition
            return False, footprint_str, {}
        
        # Demand dry-up is still relevant for flat bases
        if not is_demand_dry(filtered_results, prices, volumes):
            return False, footprint_str, {}
        is_vol_dry, _ = is_volume_dry_up_at_pivot(volumes, int(last_low_idx))
        if not is_vol_dry:
            return False, footprint_str, {}
        return True, footprint_str, {}

    # Full mode (detailed checks)
    bool_checks: dict[str, bool] = {
        "is_pivot_good": is_pivot_good(filtered_results, prices[-1]),
        # invert is_correction_deep so True means "not too deep"
        "is_correction_deep": not is_correction_deep(filtered_results),
        "is_demand_dry": is_demand_dry(filtered_results, prices, volumes),
    }
    is_vol_dry, vol_dry_ratio = is_volume_dry_up_at_pivot(volumes, int(last_low_idx))
    bool_checks["is_volume_dry_at_pivot"] = is_vol_dry

    vcp_pass_status = all(bool_checks.values())
    details: dict[str, Any] = {
        **bool_checks,
        # expose the quantitative volume metric for UI / monitoring
        "volume_dry_up_ratio": vol_dry_ratio,
        # Expose the clean, filtered contractions for visualization
        "filtered_contractions": filtered_results, 
        "is_flat_base": is_flat_base # Expose this for UI/Debugging
    }

    return vcp_pass_status, footprint_str, details
    
# Freshness evaluation
def check_pivot_freshness(vcp_results: List[Any], prices: List[float]) -> dict:
    """
    Checks if the most recent VCP pivot point is still actionable.

    An actionable pivot is "fresh" and has not already broken out.
    1. Freshness: The low of the last contraction occurred within PIVOT_FRESHNESS_DAYS.
    2. Not Broken Out: The current price is not significantly above the last high (pivot buy point).

    Args:
        vcp_results: A list of VCP contraction tuples/lists [(high_idx, high_price, low_idx, low_price), ...].
        prices: The full list of historical closing prices (chronologically sorted).

    Returns:
        A dictionary with 'passes' (bool), 'days_since_pivot' (int|None), and 'message' (str).
    """
    if not vcp_results:
        return {
            "passes": False,
            "days_since_pivot": None,
            "message": "No VCP detected to check for freshness."
        }

    last_high_price = float(vcp_results[-1][1])
    last_low_idx = int(vcp_results[-1][2])
    current_price = float(prices[-1])

    # 1) Time-based freshness: pivot low within freshness window
    days_since_pivot = (len(prices) - 1) - last_low_idx
    if days_since_pivot > PIVOT_FRESHNESS_DAYS:
        return {
            "passes": False,
            "days_since_pivot": days_since_pivot,
            "message": f"Pivot is stale. Formed {days_since_pivot} days ago (max {PIVOT_FRESHNESS_DAYS})."
        }

    # 2) Breakout/extension check: price not extended beyond threshold above pivot high
    if current_price > (last_high_price * PIVOT_BREAKOUT_THRESHOLD):
        pct = int(round((PIVOT_BREAKOUT_THRESHOLD - 1.0) * 100))
        return {
            "passes": False,
            "days_since_pivot": days_since_pivot,
            "message": f"Possible breakout in progress. Current price is >{pct}% above pivot high."
        }

    return {
        "passes": True,
        "days_since_pivot": days_since_pivot,
        "message": f"Pivot is fresh (formed {days_since_pivot} days ago) and is not extended."
    }