// frontend-app/src/hooks/useStockData.test.js
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStockData } from './useStockData';
import * as api from '../services/api';

// Mock the entire api module
vi.mock('../services/api');

describe('hooks/useStockData', () => {

    it('should return the correct initial state', () => {
        // Arrange & Act
        const { result } = renderHook(() => useStockData('GOOG'));

        // Assert
        expect(result.current.ticker).toBe('GOOG');
        expect(result.current.data).toEqual({ screening: null, analysis: null });
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBe(null);
    });

    it('should handle the full data fetching lifecycle successfully', async () => {
        // Arrange
        const mockData = { screening: { passes: true }, analysis: { detected: true } };
        vi.spyOn(api, 'fetchStockData').mockResolvedValue(mockData);
        const { result } = renderHook(() => useStockData());

        // Act
        await act(async () => {
            await result.current.getData('TSLA');
        });

        // Assert
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBe(null);
        expect(result.current.data).toEqual(mockData);
        expect(api.fetchStockData).toHaveBeenCalledWith('TSLA');
    });

    it('should handle errors from the API call', async () => {
        // Arrange
        const errorMessage = 'API request failed';
        vi.spyOn(api, 'fetchStockData').mockRejectedValue(new Error(errorMessage));
        const { result } = renderHook(() => useStockData());

        // Act
        await act(async () => {
            await result.current.getData('FAIL');
        });

        // Assert
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBe(errorMessage);
        expect(result.current.data).toEqual({ screening: null, analysis: null });
    });

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