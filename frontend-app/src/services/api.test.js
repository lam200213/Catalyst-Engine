import { describe, it, expect, vi, afterEach } from 'vitest';
import axios from 'axios';
import { fetchStockData } from './api';

// Mock the axios library
vi.mock('axios');

describe('services/api', () => {
    afterEach(() => {
        vi.restoreAllMocks();
    });

    // Test Case 1: Business Logic Verification (Successful fetch)
    it('should fetch screening and analysis data successfully', async () => {
        // Arrange: Mock successful responses from both services
        const mockScreeningData = { ticker: 'AAPL', passes: true };
        const mockAnalysisData = { ticker: 'AAPL', analysis: { detected: true } };

        axios.get.mockImplementation(url => {
            if (url.includes('/screen/')) {
                return Promise.resolve({ data: mockScreeningData });
            }
            if (url.includes('/analyze/')) {
                return Promise.resolve({ data: mockAnalysisData });
            }
            return Promise.reject(new Error('Unknown endpoint'));
        });

        // Act: Call the function
        const result = await fetchStockData('AAPL');

        // Assert: Verify the results and that axios was called correctly
        expect(axios.get).toHaveBeenCalledTimes(2);
        expect(axios.get).toHaveBeenCalledWith('http://localhost:3000/screen/AAPL');
        expect(axios.get).toHaveBeenCalledWith('http://localhost:3000/analyze/AAPL');
        expect(result).toEqual({
            screening: mockScreeningData,
            analysis: mockAnalysisData
        });
    });

    // Test Case 2: Edge Case (API returns an error)
    it('should throw a standardized error if the API responds with an error', async () => {
        // Arrange: Mock a rejected promise with a specific error structure
        const apiError = { response: { data: { error: 'Invalid Ticker' } } };
        axios.get.mockRejectedValue(apiError);

        // Act & Assert: Expect the function to throw the custom error message
        await expect(fetchStockData('INVALID')).rejects.toThrow('Invalid Ticker');
    });

    // Test Case 3: Edge Case (Network error)
    it('should throw a generic error for network failures', async () => {
        // Arrange: Mock a generic network error
        axios.get.mockRejectedValue(new Error('Network Error'));

        // Act & Assert: Expect the function to throw the generic error message
        await expect(fetchStockData('ANYTICKER')).rejects.toThrow('Network Error');
    });

    // Test Case 4: Security/Consistency (No security implications found, checks for consistency)
    it('should use the VITE_API_BASE_URL environment variable if available', async () => {
        // Arrange: Set the environment variable
        const originalEnv = import.meta.env.VITE_API_BASE_URL;
        import.meta.env.VITE_API_BASE_URL = 'https://api.example.com';

        axios.get.mockResolvedValue({ data: {} });

        // Act
        await fetchStockData('TEST');

        // Assert
        expect(axios.get).toHaveBeenCalledWith('https://api.example.com/screen/TEST');
        expect(axios.get).toHaveBeenCalledWith('https://api.example.com/analyze/TEST');

        // Cleanup
        import.meta.env.VITE_API_BASE_URL = originalEnv;
    });
});