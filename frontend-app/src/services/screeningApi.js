// frontend-app/src/services/screeningApi.js
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:3000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

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

/**
 * Fetches screening result for a single ticker.
 * @param {string} ticker - The stock ticker symbol.
 * @returns {Promise} Screening result.
 */
export const getScreeningResult = (ticker) => apiClient.get(`/screen/${ticker}`);

/**
 * Fetches VCP analysis for a single ticker.
 * @param {string} ticker - The stock ticker symbol.
 * @param {string} [mode='full'] - 'full' or 'fast' mode.
 * @returns {Promise} VCP analysis result.
 */
export const getVCPAnalysis = (ticker, mode = 'full') => 
  apiClient.get(`/analyze/${ticker}`, { params: { mode } });

/**
 * Fetches leadership profile for a single ticker.
 * @param {string} ticker - The stock ticker symbol.
 * @returns {Promise} Leadership profile result.
 */
export const getLeadershipProfile = (ticker) => apiClient.get(`/leadership/${ticker}`);