// frontend-app/src/services/api.js
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:3000';

/**
 * Fetches both screening and analysis data for a given ticker.
 * @param {string} ticker - The stock ticker symbol.
 * @returns {Promise<Object>} An object containing screening and analysis results.
 */
export const fetchStockData = async (ticker) => {
    try {
        const screeningPromise = axios.get(`${API_BASE_URL}/screen/${ticker}`);
        const analysisPromise = axios.get(`${API_BASE_URL}/analyze/${ticker}`);

        const [screeningRes, analysisRes] = await Promise.all([screeningPromise, analysisPromise]);

        return {
            screening: screeningRes.data,
            analysis: analysisRes.data,
        };
    } catch (err) {
        // Rethrow the error to be handled by the calling hook/component
        const errorMessage = err.response?.data?.error || err.message || "An unknown error occurred.";
        throw new Error(errorMessage);
    }
};