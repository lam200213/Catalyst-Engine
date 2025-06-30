require('dotenv').config({ path: '../../.env' });
const express = require('express');
const axios = require('axios');

const app = express();
const PORT = process.env.PORT || 3002;
const DATA_SERVICE_URL = process.env.DATA_SERVICE_URL || 'http://localhost:3001';

app.use(express.json());

// Placeholder for screening logic (from TrendTemplate_MarkMinervini_Indicator.cs)
function applyScreeningCriteria(fundamentals) {
  // This is a simplified placeholder. Real logic would be complex.
  // Example criteria:
  // - EPS growth
  // - Sales growth
  // - Profit margins
  // - ROE
  // - Debt/Equity ratio
  // - Institutional ownership
  // - Relative Strength
  // - Price above moving averages

  if (!fundamentals || Object.keys(fundamentals).length === 0) {
    return { passes: false, reason: "No fundamental data available" };
  }

  // Mock criteria for demonstration
  const passes = fundamentals.marketCapitalization > 1000000000 && fundamentals.shareOutstanding > 0;

  return {
    passes: passes,
    reason: passes ? "Meets basic criteria" : "Does not meet basic criteria",
    details: fundamentals // For debugging, show what data was used
  };
}

// API Endpoint for screening
app.get('/screen/:ticker', async (req, res) => {
  const ticker = req.params.ticker.toUpperCase();
  try {
    // Call data-service to get fundamental data
    const fundamentalsResponse = await axios.get(`${DATA_SERVICE_URL}/data/fundamentals/${ticker}`);
    const fundamentals = fundamentalsResponse.data;

    const screeningResult = applyScreeningCriteria(fundamentals);

    res.json({
      ticker: ticker,
      ...screeningResult
    });
  } catch (error) {
    console.error(`Error screening ${ticker}:`, error.message);
    res.status(500).json({ error: `Failed to screen ticker: ${error.message}` });
  }
});

app.listen(PORT, () => {
  console.log(`Screening Service listening on port ${PORT}`);
});
