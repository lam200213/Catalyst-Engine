require('dotenv').config({ path: '../../.env' });
const express = require('express');
const axios = require('axios');

const app = express();
const PORT = process.env.PORT || 3003;
// Use Docker service name from environment variable
const DATA_SERVICE_URL = process.env.DATA_SERVICE_URL || 'http://data-service:3001';

app.use(express.json());

// Placeholder for VCP detection logic (from "cookstock" Python script)
function detectVCP(historicalData) {
  // This is a highly simplified placeholder.
  // Real VCP detection involves complex pattern recognition on price and volume.
  // It would typically look for:
  // 1. Prior uptrend
  // 2. Contraction in volatility (tighter price ranges)
  // 3. Decreasing volume during contractions
  // 4. Pivot point (breakout)

  if (!historicalData || !historicalData.c || historicalData.c.length < 50) {
    return {
      detected: false,
      message: "Not enough historical data for VCP analysis.",
      vcpLines: [],
      buyPoints: [],
      sellPoints: []
    };
  }

  // Mock VCP lines and points for demonstration
  const prices = historicalData.c; // Closing prices
  const volumes = historicalData.v; // Volumes

  const lastIndex = prices.length - 1;
  const secondLastIndex = prices.length - 2;

  const vcpLines = [
    {
      price: prices[lastIndex] * 0.95, // Support line
      time: historicalData.t[lastIndex - 10] // Start 10 days ago
    },
    {
      price: prices[lastIndex] * 1.05, // Resistance line
      time: historicalData.t[lastIndex - 10]
    },
    {
      price: prices[lastIndex] * 0.95,
      time: historicalData.t[lastIndex]
    },
    {
      price: prices[lastIndex] * 1.05,
      time: historicalData.t[lastIndex]
    }
  ];

  const buyPoints = [
    { price: prices[secondLastIndex], time: historicalData.t[secondLastIndex] }
  ];

  const sellPoints = []; // No sell points in this simple mock

  return {
    detected: true, // Mock result
    message: "VCP analysis performed (mock data).",
    vcpLines: vcpLines,
    buyPoints: buyPoints,
    sellPoints: sellPoints,
    debug: {
      lastPrice: prices[lastIndex],
      lastVolume: volumes[lastIndex]
    }
  };
}

// API Endpoint for analysis
app.get('/analyze/:ticker', async (req, res) => {
  const ticker = req.params.ticker.toUpperCase();
  try {
    // Call data-service to get historical price/volume data
    const historicalPriceResponse = await axios.get(`${DATA_SERVICE_URL}/data/historical-price/${ticker}`);
    const historicalData = historicalPriceResponse.data;

    const analysisResult = detectVCP(historicalData);

    // Always return the analysis result AND the historical data
    res.json({
      ticker: ticker,
      analysis: analysisResult,
      historicalData: historicalData // Pass the raw data for charting
    });
  } catch (error) {
    console.error(`Error analyzing ${ticker}:`, error.message);
    res.status(500).json({ error: `Failed to analyze ticker: ${error.message}` });
  }
});

app.listen(PORT, () => {
  console.log(`Analysis Service listening on port ${PORT}`);
});
