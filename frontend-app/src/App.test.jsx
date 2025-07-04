// frontend-app/src/App.test.jsx
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChakraProvider } from '@chakra-ui/react';
import App from './App';
import * as api from './services/api';

// Mock the lightweight-charts library
vi.mock('lightweight-charts', () => ({
    createChart: vi.fn(() => ({
        addCandlestickSeries: vi.fn(() => ({ setData: vi.fn() })),
        addHistogramSeries: vi.fn(() => ({ setData: vi.fn() })),
        addLineSeries: vi.fn(() => ({ setData: vi.fn() })),
        remove: vi.fn(),
        timeScale: () => ({ fitContent: vi.fn() }),
        applyOptions: vi.fn(),
    })),
    ColorType: { Solid: 'solid' },
}));

// Mock the api service module
vi.mock('./services/api');

describe('App Component Integration Test', () => {

    // Clear all mocks before each test runs to ensure test isolation
    beforeEach(() => {
        vi.clearAllMocks();
    });

    // Helper function to render the App with ChakraProvider
    const renderApp = () => {
        render(
            <ChakraProvider>
                <App />
            </ChakraProvider>
        );
    };

    // Test for initial component rendering
    it('should render the main layout with all child components on initial load', () => {
        renderApp();
        // Check for TickerForm by its input placeholder
        expect(screen.getByPlaceholderText(/Enter Ticker/i)).toBeInTheDocument();
        // Check for ScreeningPanel by its heading
        expect(screen.getByRole('heading', { name: /Screening Results/i })).toBeInTheDocument();
        // Check for ChartPanel by its heading
        expect(screen.getByRole('heading', { name: /VCP Analysis/i })).toBeInTheDocument();
    });

    // Integration test for the main application view (success case)
    it('should render data on successful form submission', async () => {
        // Arrange: Mock a successful API response
        const mockSuccessData = {
            screening: { ticker: 'AAPL', passes: true, details: { current_price_above_ma50: true } },
            analysis: { ticker: 'AAPL', analysis: { message: 'VCP analysis complete.' } }
        };
        api.fetchStockData.mockResolvedValue(mockSuccessData);
        
        const user = userEvent.setup();
        renderApp();
        
        // Act: Simulate user input and form submission
        const input = screen.getByPlaceholderText(/Enter Ticker/i);
        const button = screen.getByRole('button', { name: /Analyze Stock/i });
        await user.clear(input);
        await user.type(input, 'AAPL');
        await user.click(button);

        // Assert: Wait for the final data to appear
        await waitFor(() => {
            // Assert that the results are displayed
            expect(screen.getByText('PASS')).toBeInTheDocument();
            expect(screen.getByText('VCP analysis complete.')).toBeInTheDocument();
        });
        
        // Assert loading state is gone
        expect(screen.queryByText(/Analyzing.../i)).not.toBeInTheDocument();
        expect(api.fetchStockData).toHaveBeenCalledWith('AAPL');
    });

    // Integration test for API failure
    it('should display an error message on API failure', async () => {
        // Arrange: Mock a failed API response
        const errorMessage = 'Invalid Ticker Provided';
        api.fetchStockData.mockRejectedValue(new Error(errorMessage));

        const user = userEvent.setup();
        renderApp();
        
        // Act: Simulate user input and form submission
        const input = screen.getByPlaceholderText(/Enter Ticker/i);
        const button = screen.getByRole('button', { name: /Analyze Stock/i });
        await user.clear(input);
        await user.type(input, 'FAIL');
        await user.click(button);
        
        // Assert: Wait for the error message to appear
        await waitFor(() => {
            const errorAlert = screen.getByRole('alert');
            expect(errorAlert).toHaveTextContent(errorMessage);
        });

        // Assert that loading state is gone
        expect(screen.queryByText(/Analyzing.../i)).not.toBeInTheDocument();
        expect(api.fetchStockData).toHaveBeenCalledWith('FAIL');
    });    
});