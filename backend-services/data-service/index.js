require('dotenv').config({ path: '../../.env' });
const express = require('express');
const mongoose = require('mongoose');
const axios = require('axios');

const app = express();
const PORT = process.env.PORT || 3001;
const MONGO_URI = process.env.MONGO_URI;
const FINNHUB_API_KEY = process.env.FINNHUB_API_KEY;

app.use(express.json());

// MongoDB Connection
mongoose.connect(MONGO_URI)
  .then(() => console.log('MongoDB connected successfully to data-service'))
  .catch(err => console.error('MongoDB connection error:', err));

// Define a simple schema for caching (example)
const StockDataSchema = new mongoose.Schema({
  ticker: { type: String, required: true, unique: true },
  data: { type: Object, required: true },
  timestamp: { type: Date, default: Date.now, expires: '1h' } // Data expires in 1 hour
});
const StockData = mongoose.model('StockData', StockDataSchema);

// Helper function to fetch data from Finnhub (placeholder)
async function fetchFromFinnhub(endpoint, params) {
  try {
    const response = await axios.get(`https://finnhub.io/api/v1/${endpoint}`, {
      params: {
        token: FINNHUB_API_KEY,
        ...params
      }
    });
    return response.data;
  } catch (error) {
    console.error(`Error fetching from Finnhub ${endpoint}:`, error.message);
    throw new Error(`Failed to fetch data from Finnhub: ${error.message}`);
  }
}

// Data fetching and caching functions
async function getHistoricalPriceData(ticker) {
  const cacheKey = `historical_price_${ticker}`;
  let cachedData = await StockData.findOne({ ticker: cacheKey });

  if (cachedData) {
    console.log(`Returning cached historical price data for ${ticker}`);
    return cachedData.data;
  }

  console.log(`Fetching historical price data for ${ticker} from Finnhub`);
  // Example: Fetch daily candles for the last year
  const now = Math.floor(Date.now() / 1000);
  const oneYearAgo = now - (365 * 24 * 60 * 60);
  const data = await fetchFromFinnhub('stock/candle', {
    symbol: ticker,
    resolution: 'D',
    from: oneYearAgo,
    to: now
  });

  await StockData.findOneAndUpdate(
    { ticker: cacheKey },
    { data: data, timestamp: Date.now() },
    { upsert: true, new: true }
  );
  return data;
}

async function getFundamentals(ticker) {
  const cacheKey = `fundamentals_${ticker}`;
  let cachedData = await StockData.findOne({ ticker: cacheKey });

  if (cachedData) {
    console.log(`Returning cached fundamentals for ${ticker}`);
    return cachedData.data;
  }

  console.log(`Fetching fundamentals for ${ticker} from Finnhub`);
  // Example: Fetch company profile
  const data = await fetchFromFinnhub('stock/profile2', { symbol: ticker });

  await StockData.findOneAndUpdate(
    { ticker: cacheKey },
    { data: data, timestamp: Date.now() },
    { upsert: true, new: true }
  );
  return data;
}

async function getNews(ticker) {
  const cacheKey = `news_${ticker}`;
  let cachedData = await StockData.findOne({ ticker: cacheKey });

  if (cachedData) {
    console.log(`Returning cached news for ${ticker}`);
    return cachedData.data;
  }

  console.log(`Fetching news for ${ticker} from Finnhub`);
  // Example: Fetch company news for the last 30 days
  const today = new Date().toISOString().split('T')[0];
  const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
  const data = await fetchFromFinnhub('company-news', {
    symbol: ticker,
    from: thirtyDaysAgo,
    to: today
  });

  await StockData.findOneAndUpdate(
    { ticker: cacheKey },
    { data: data, timestamp: Date.now() },
    { upsert: true, new: true }
  );
  return data;
}

// API Endpoints
app.get('/data/historical-price/:ticker', async (req, res) => {
  try {
    const data = await getHistoricalPriceData(req.params.ticker);
    res.json(data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/data/fundamentals/:ticker', async (req, res) => {
  try {
    const data = await getFundamentals(req.params.ticker);
    res.json(data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/data/news/:ticker', async (req, res) => {
  try {
    const data = await getNews(req.params.ticker);
    res.json(data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.listen(PORT, () => {
  console.log(`Data Service listening on port ${PORT}`);
});
