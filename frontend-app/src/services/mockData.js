// frontend-app/src/services/mockData.js

/**
 * @typedef {object} LeadingStock
 * @property {string} ticker
 * @property {number} percent_change_1m
 */

/**
 * @typedef {object} LeadingIndustry
 * @property {string} industry
 * @property {LeadingStock[]} stocks
 */

/**
 * @typedef {object} MarketLeaders
 * @property {LeadingIndustry[]} leading_industries
 */

/**
 * @typedef {object} MarketOverview
 * @property {'Bullish' | 'Bearish' | 'Neutral' | 'Recovery'} market_stage
 * @property {number} market_correction_depth - Note: Renamed from correction_depth_percent to match backend contract
 * @property {number} new_highs
 * @property {number} new_lows
 * @property {number} high_low_ratio
 */

/**
 * This mock data strictly follows the MarketHealthResponse contract.
 * @type {{market_overview: MarketOverview, leaders_by_industry: MarketLeaders}}
 */
export const mockMarketHealthResponse = {
  market_overview: {
    market_stage: 'Bullish',
    market_correction_depth: -4.8,
    new_highs: 210,
    new_lows: 45,
    high_low_ratio: 4.67,
  },
  leaders_by_industry: {
    leading_industries: [
      {
        industry: 'Semiconductors',
        stocks: [
          { ticker: 'NVDA', percent_change_1m: 18.2 },
          { ticker: 'AVGO', percent_change_1m: 12.5 },
        ],
      },
      {
        industry: 'Software - Infrastructure',
        stocks: [
          { ticker: 'CRWD', percent_change_1m: 21.7 },
          { ticker: 'NET', percent_change_1m: 16.3 },
        ],
      },
      {
        industry: 'Biotechnology',
        stocks: [
            { ticker: 'VRTX', percent_change_1m: 9.8 },
        ]
      }
    ],
  },
};