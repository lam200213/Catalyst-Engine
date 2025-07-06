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
        addCandlestickSeries: vi.fn(() => ({ setData: vi.fn(), createPriceLine: vi.fn(), setMarkers: vi.fn() })),
        addHistogramSeries: vi.fn(() => ({ setData: vi.fn(), createPriceLine: vi.fn() })),
        addLineSeries: vi.fn(() => ({ setData: vi.fn() })),
        // Latest Add: Add missing mock functions to prevent component crash
        subscribeCrosshairMove: vi.fn(),
        unsubscribeCrosshairMove: vi.fn(),
        remove: vi.fn(),
        timeScale: () => ({ fitContent: vi.fn() }),
        priceScale: () => ({ applyOptions: vi.fn() }),
        applyOptions: vi.fn(),
    })),
    ColorType: { Solid: 'solid' },
    LineStyle: { Dashed: 1, Dotted: 2 },
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
    // Ttest dedicated to verifying the loading state.
    it('should display loading indicators while fetching data', async () => {
        // Arrange: Use a mock promise that never resolves to freeze the app in a loading state.
        api.fetchStockData.mockReturnValue(new Promise(() => {}));
        const user = userEvent.setup();
        renderApp();
        
        // Act: Simulate user input and form submission
        const input = screen.getByPlaceholderText(/Enter Ticker/i);
        const button = screen.getByRole('button', { name: /Analyze Stock/i });
        await user.clear(input);
        await user.type(input, 'AAPL');
        await user.click(button);

        // Assert: The app is now permanently in a loading state for this test.
        // We can now reliably check for the loading indicators.
        expect(screen.getByText(/Analyzing.../i)).toBeInTheDocument();
        // The accessible name for Chakra's Spinner is "Loading..."
        expect(screen.getAllByText('Loading...').length).toBeGreaterThan(0);
        expect(button).toBeDisabled(); // The button should be disabled while loading.
    });

    //  A focused test for the successful outcome.
    it('should render data after a successful form submission', async () => {
        // Arrange: Mock a successful API response.
        const mockSuccessData = {
            screening: { ticker: 'AAPL', passes: true, details: { current_price_above_ma50: true } },
            analysis: { analysis: { message: 'VCP analysis complete.' } }
        };
        api.fetchStockData.mockResolvedValue(mockSuccessData);
        
        const user = userEvent.setup();
        renderApp();
        
        // Act
        const input = screen.getByPlaceholderText(/Enter Ticker/i);
        const button = screen.getByRole('button', { name: /Analyze Stock/i });
        await user.clear(input);
        await user.type(input, 'AAPL');
        await user.click(button);

        // Assert: Wait only for the final data to appear.
        await waitFor(() => {
            expect(screen.getByText('PASS')).toBeInTheDocument();
            expect(screen.getByText('VCP analysis complete.')).toBeInTheDocument();
        });
        
        // Final sanity check that the loading state is gone.
        expect(screen.queryByText(/Analyzing.../i)).not.toBeInTheDocument();
        expect(api.fetchStockData).toHaveBeenCalledWith('AAPL');
    });

    // Integration test for API failure
    // Specific test for a "Not Found" or "Bad Gateway" error
    it('should display a specific error for an invalid ticker', async () => {
        // Arrange
        const errorMessage = 'Invalid or non-existent ticker: FAKETICKER';
        api.fetchStockData.mockRejectedValue(new Error(errorMessage));
        const user = userEvent.setup();
        renderApp();

        // Act: Simulate user input and form submission
        const input = screen.getByPlaceholderText(/Enter Ticker/i);
        const button = screen.getByRole('button', { name: /Analyze Stock/i });
        await user.clear(input);
        await user.type(input, 'FAKETICKER');
        await user.click(button);
        
        // Check loading state during the request
        // Assert: Wait for the error message to appear
        await waitFor(() => {
            const errorAlert = screen.getByRole('alert');
            expect(errorAlert).toHaveTextContent(errorMessage);
        });
        expect(api.fetchStockData).toHaveBeenCalledWith('FAKETICKER');
    });

    // Specific test for a generic server or connection error
    it('should display a generic error for a server failure', async () => {
        // Arrange
        const errorMessage = 'Service unavailable: data-service';
        api.fetchStockData.mockRejectedValue(new Error(errorMessage));
        const user = userEvent.setup();
        renderApp();

        // Act
        const input = screen.getByPlaceholderText(/Enter Ticker/i);
        const button = screen.getByRole('button', { name: /Analyze Stock/i });
        await user.clear(input);
        await user.type(input, 'ANY');
        await user.click(button);

        // Assert
        await waitFor(() => {
            const errorAlert = screen.getByRole('alert');
            expect(errorAlert).toHaveTextContent(errorMessage);
        });
        expect(api.fetchStockData).toHaveBeenCalledWith('ANY');
    });

    // TEST: Security test for XSS
    it('should correctly handle and escape malicious script input', async () => {
        const maliciousInput = '<script>alert("XSS")</script>';
        // The expected string is corrected to what React actually renders (escaped HTML).
        const escapedHtml = '&lt;script&gt;alert("XSS")&lt;/script&gt;';
        const errorMessage = `Invalid Ticker: ${maliciousInput}`;
        
        api.fetchStockData.mockRejectedValue(new Error(errorMessage));
        
        const user = userEvent.setup();
        renderApp();

        const input = screen.getByPlaceholderText(/Enter Ticker/i);
        const button = screen.getByRole('button', { name: /Analyze Stock/i });

        await user.clear(input);
        await user.type(input, maliciousInput);
        await user.click(button);

        await waitFor(() => {
            const errorAlert = screen.getByRole('alert');
            // Assert that the alert's innerHTML contains the ESCAPED version of the input
            expect(errorAlert.innerHTML).toContain(escapedHtml);
            // Assert that the raw, unescaped text is NOT present
            expect(screen.queryByText(maliciousInput)).toBeNull();
        });
        
        // Assert that the API was called with the UPPERCASED version of the input.
        expect(api.fetchStockData).toHaveBeenCalledWith(maliciousInput.toUpperCase());
    });
});