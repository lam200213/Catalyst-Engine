// frontend-app/src/hooks/useStockData.js
import { useState } from 'react';
import { fetchStockData } from '../services/api';

export const useStockData = (initialTicker = 'AAPL') => {
    const [ticker, setTicker] = useState(initialTicker);
    const [data, setData] = useState({ screening: null, analysis: null });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const getData = async (tickerSymbol) => {
        setLoading(true);
        setError(null);
        setData({ screening: null, analysis: null });

        try {
            const results = await fetchStockData(tickerSymbol);
            setData({
                screening: results.screening,
                analysis: results.analysis,
            });
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return { ticker, setTicker, data, loading, error, getData };
};