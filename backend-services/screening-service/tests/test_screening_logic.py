import unittest
import numpy as np
from app import apply_screening_criteria, calculate_sma

class TestScreeningLogic(unittest.TestCase):

    def generate_passing_data(self):
        """
        Generates mock historical price data that should pass all 7 screening criteria.
        Approximately 300 prices.
        """
        prices = []
        # Ensure MA200 is trending up
        # Ensure MA50 > MA150 > MA200
        # Ensure current price > MA50
        # Ensure current price is > 30% above 52-week low
        # Ensure current price is within 25% of 52-week high

        # Start with a base price and gradually increase
        base_price = 100.0
        for i in range(300):
            # Simulate an uptrend
            price = base_price + i * 0.5 + np.random.uniform(-2, 2)
            prices.append(price)
        
        # Adjust last few prices to ensure current_price > MA50
        # and MA50 > MA150 > MA200
        # and MA200 trending up
        # and 52-week high/low conditions
        
        # Ensure MA200 is trending up
        # Make sure the last 200-day MA is higher than the 200-day MA from a month ago (20 trading days)
        # For simplicity, ensure overall uptrend
        
        # Ensure 52-week low/high conditions
        # Let's make the last 252 days (approx 52 weeks) relevant
        recent_prices = prices[-252:]
        current_price = prices[-1]
        
        low_52_week_target = current_price / 1.35 # Ensure current price is > 30% above this
        high_52_week_target = current_price / 0.8 # Ensure current price is within 25% of this (i.e., current_price >= 0.75 * high_52_week)

        # Artificially set some values to guarantee conditions for the last 252 days
        # This is a bit hacky for a unit test, but ensures the conditions are met
        min_val_for_52_week_low = low_52_week_target * 0.9 # Slightly below target to allow for random fluctuations
        max_val_for_52_week_high = high_52_week_target * 1.1 # Slightly above target

        for i in range(len(recent_prices)):
            if recent_prices[i] < min_val_for_52_week_low:
                recent_prices[i] = min_val_for_52_week_low + np.random.uniform(0, 1)
            if recent_prices[i] > max_val_for_52_week_high:
                recent_prices[i] = max_val_for_52_week_high - np.random.uniform(0, 1)
        
        prices[-252:] = recent_prices

        # Ensure MAs are in correct order and current price is above MA50
        # This part is tricky with random data, so we'll ensure the trend is strong
        # and the last price is high enough.
        # For a robust unit test, one might manually construct the last N prices.
        # For now, rely on the strong uptrend and sufficient length.

        return {'c': prices}

    def generate_failing_data(self, failure_type="death_cross"):
        """
        Generates mock historical price data that should fail specific screening criteria.
        """
        prices = []
        base_price = 200.0
        for i in range(300):
            prices.append(base_price - i * 0.1 + np.random.uniform(-1, 1)) # Downtrend

        if failure_type == "death_cross":
            # Simulate MA50 crossing below MA150
            # Make recent prices drop significantly
            for i in range(50):
                prices[-50 + i] = 100 - i * 0.5 + np.random.uniform(-1, 1)
        elif failure_type == "ma200_down":
            # Ensure MA200 is trending down
            base_price = 200.0
            for i in range(300):
                prices.append(base_price - i * 0.5 + np.random.uniform(-2, 2)) # Strong downtrend
        elif failure_type == "below_52_week_low_30_percent":
            # Current price is not 30% above 52-week low
            prices = [100 + np.random.uniform(-5, 5) for _ in range(300)]
            prices[-252] = 50 # Set a very low 52-week low
            prices[-1] = 55 # Current price is not 30% above 50 (50 * 1.3 = 65)
        elif failure_type == "not_within_25_percent_of_52_week_high":
            # Current price is not within 25% of 52-week high
            prices = [100 + np.random.uniform(-5, 5) for _ in range(300)]
            prices[-252] = 200 # Set a very high 52-week high
            prices[-1] = 100 # Current price is not within 25% of 200 (200 * 0.75 = 150)
        
        return {'c': prices}

    def test_stock_passes_all_criteria(self):
        ticker = "PASS"
        historical_data = self.generate_passing_data()
        result = apply_screening_criteria(ticker, historical_data)

        self.assertTrue(result['passes'], "Stock should pass all criteria")
        self.assertTrue(result['details']['current_price_above_ma150_ma200'])
        self.assertTrue(result['details']['ma150_above_ma200'])
        self.assertTrue(result['details']['ma200_trending_up'])
        self.assertTrue(result['details']['ma50_above_ma150_ma200'])
        self.assertTrue(result['details']['current_price_above_ma50'])
        self.assertTrue(result['details']['price_30_percent_above_52_week_low'])
        self.assertTrue(result['details']['price_within_25_percent_of_52_week_high'])

    def test_stock_fails_ma50_below_ma150(self):
        ticker = "FAIL_MA50"
        historical_data = self.generate_failing_data(failure_type="death_cross")
        result = apply_screening_criteria(ticker, historical_data)

        self.assertFalse(result['passes'], "Stock should fail due to MA50 below MA150")
        self.assertFalse(result['details']['ma50_above_ma150_ma200'])

    def test_stock_fails_ma200_trending_down(self):
        ticker = "FAIL_MA200_TREND"
        historical_data = self.generate_failing_data(failure_type="ma200_down")
        result = apply_screening_criteria(ticker, historical_data)

        self.assertFalse(result['passes'], "Stock should fail due to MA200 trending down")
        self.assertFalse(result['details']['ma200_trending_up'])

    def test_stock_fails_below_30_percent_above_52_week_low(self):
        ticker = "FAIL_LOW_30"
        historical_data = self.generate_failing_data(failure_type="below_52_week_low_30_percent")
        result = apply_screening_criteria(ticker, historical_data)

        self.assertFalse(result['passes'], "Stock should fail due to not being 30% above 52-week low")
        self.assertFalse(result['details']['price_30_percent_above_52_week_low'])

    def test_stock_fails_not_within_25_percent_of_52_week_high(self):
        ticker = "FAIL_HIGH_25"
        historical_data = self.generate_failing_data(failure_type="not_within_25_percent_of_52_week_high")
        result = apply_screening_criteria(ticker, historical_data)

        self.assertFalse(result['passes'], "Stock should fail due to not being within 25% of 52-week high")
        self.assertFalse(result['details']['price_within_25_percent_of_52_week_high'])

    def test_insufficient_data(self):
        ticker = "INSUFFICIENT"
        historical_data = {'c': [100, 101, 102]} # Not enough data for MAs
        result = apply_screening_criteria(ticker, historical_data)
        self.assertFalse(result['passes'])
        # When data is insufficient but not empty, it will still try to calculate and return details/values
        # The individual criteria will be False because MAs will be None
        self.assertFalse(result['details']['current_price_above_ma150_ma200'])
        self.assertFalse(result['details']['ma150_above_ma200'])
        self.assertFalse(result['details']['ma200_trending_up'])
        self.assertFalse(result['details']['ma50_above_ma150_ma200'])
        self.assertFalse(result['details']['current_price_above_ma50'])
        self.assertFalse(result['details']['price_30_percent_above_52_week_low'])
        self.assertFalse(result['details']['price_within_25_percent_of_52_week_high'])

    def test_empty_data(self):
        ticker = "EMPTY"
        historical_data = {'c': []}
        result = apply_screening_criteria(ticker, historical_data)
        self.assertFalse(result['passes'])
        self.assertIn('reason', result)
        self.assertEqual(result['reason'], "Insufficient historical price data.")
        self.assertEqual(result['details'], {})
        self.assertEqual(result['values'], {})

    def test_none_data(self):
        ticker = "NONE"
        historical_data = None
        result = apply_screening_criteria(ticker, historical_data)
        self.assertFalse(result['passes'])
        self.assertIn('reason', result)
        self.assertEqual(result['reason'], "Insufficient historical price data.")
        self.assertEqual(result['details'], {})
        self.assertEqual(result['values'], {})

    def test_sma_calculation(self):
        prices = [i for i in range(1, 11)] # [1, 2, ..., 10]
        self.assertEqual(calculate_sma(prices, 5), 8.0) # (6+7+8+9+10)/5
        self.assertEqual(calculate_sma(prices, 10), 5.5) # (1+..+10)/10
        self.assertIsNone(calculate_sma(prices, 11)) # Insufficient data

if __name__ == '__main__':
    unittest.main()