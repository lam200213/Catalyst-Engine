import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStockData } from './useStockData';
import * as api from '../services/api'; // Import all exports from api

// Mock the entire api module
vi.mock('../services/api');

describe('hooks/useStockData', () => {

    // Test Case 1: Business Logic Verification (Initial State)
    it('should return the correct initial state', () => {
        // Arrange & Act: Render the hook
        const { result } = renderHook(() => useStockData('GOOG'));

        // Assert: Check if the initial values are set correctly
        expect(result.current.ticker).toBe('GOOG');
        expect(result.current.data).toEqual({ screening: null, analysis: null });
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBe(null);
    });

    // Test Case 2: Business Logic Verification (Successful data fetching flow)
    it('should handle the full data fetching lifecycle successfully', async () => {
        // Arrange: Mock the API call to succeed
        const mockData = { screening: { passes: true }, analysis: { detected: true } };
        vi.spyOn(api, 'fetchStockData').mockResolvedValue(mockData);

        const { result } = renderHook(() => useStockData());

        // Act: Trigger the data fetch
        const fetchPromise = act(async () => {
            await result.current.getData('TSLA');
        });

        // Assert: Check loading state immediately after calling
        expect(result.current.loading).toBe(true);

        // Wait for the async operation to complete
        await fetchPromise;

        // Assert: Check final state
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBe(null);
        expect(result.current.data).toEqual(mockData);
        expect(api.fetchStockData).toHaveBeenCalledWith('TSLA');
    });

    // Test Case 3: Edge Case (API call fails)
    it('should handle errors from the API call', async () => {
        // Arrange: Mock the API call to fail
        const errorMessage = 'API request failed';
        vi.spyOn(api, 'fetchStockData').mockRejectedValue(new Error(errorMessage));
        
        const { result } = renderHook(() => useStockData());

        // Act
        await act(async () => {
            await result.current.getData('FAIL');
        });

        // Assert: Check that error state is set and data is empty
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBe(errorMessage);
        expect(result.current.data).toEqual({ screening: null, analysis: null });
    });

    // Test Case 4: Consistency (Setter function updates the ticker)
    it('should update the ticker when setTicker is called', () => {
        // Arrange
        const { result } = renderHook(() => useStockData('Initial'));
        
        // Act
        act(() => {
            result.current.setTicker('Updated');
        });

        // Assert
        expect(result.current.ticker).toBe('Updated');
    });
});