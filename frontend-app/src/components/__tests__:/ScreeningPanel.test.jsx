// frontend-app/src/components/ScreeningPanel.test.jsx
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ChakraProvider } from '@chakra-ui/react';
import ScreeningPanel from './ScreeningPanel';

// Mock data that mimics the API response structure
const passingData = {
    ticker: 'AAPL',
    passes: true,
    details: {
        current_price_above_ma150_ma200: true,
        ma150_above_ma200: true,
        ma200_trending_up: true,
        ma50_above_ma150_ma200: true,
        current_price_above_ma50: true,
        price_30_percent_above_52_week_low: true,
        price_within_25_percent_of_52_week_high: true
    }
};

const failingData = {
    ticker: 'FAIL',
    passes: false,
    reason: "MA50 is not above MA150",
    details: {
        current_price_above_ma150_ma200: true,
        ma150_above_ma200: true,
        ma200_trending_up: true,
        ma50_above_ma150_ma200: false,
        current_price_above_ma50: true,
        price_30_percent_above_52_week_low: true,
        price_within_25_percent_of_52_week_high: true
    }
};

describe('components/ScreeningPanel', () => {

    const renderWithProvider = (ui) => {
        return render(<ChakraProvider>{ui}</ChakraProvider>);
    };
    
    // Test Case 1: Business Logic (Loading state)
    it('should display a loading spinner when loading is true', () => {
        renderWithProvider(<ScreeningPanel result={null} loading={true} />);
        expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    // Test Case 2: Business Logic (PASS state)
    it('should display PASS and the criteria for passing data', () => {
        renderWithProvider(<ScreeningPanel result={passingData} loading={false} />);
        expect(screen.getByText('PASS')).toBeInTheDocument();
        expect(screen.getByText(/ma150 above ma200/i)).toBeInTheDocument();
    });

    // Test Case 3: Business Logic (FAIL state)
    it('should display FAIL for failing data', () => {
        renderWithProvider(<ScreeningPanel result={failingData} loading={false} />);
        expect(screen.getByText('FAIL')).toBeInTheDocument();
        expect(screen.getByText(/MA50 is not above MA150/i)).toBeInTheDocument();
    });

    // Test Case 4: Edge Case (Null props)
    it('should display a default message when props are null', () => {
        renderWithProvider(<ScreeningPanel result={null} loading={false} />);
        expect(screen.getByText('Results will appear here.')).toBeInTheDocument();
    });

    // Test Case 5: Edge Case (Malicious data)
    it('should render potentially malicious text as plain text', () => {
        const maliciousData = {
            ticker: '<script>alert("XSS")</script>',
            passes: false,
            reason: 'Malicious reason',
            details: {}
        };
        renderWithProvider(<ScreeningPanel result={maliciousData} loading={false} />);
        // Find the parent element and assert its text content to handle cases where text is broken up by other elements or spacing.
        const parentElement = screen.getByText(/Overall Result for/i);
        expect(parentElement.textContent).toContain(maliciousData.ticker);
    });

    // Test Case 6: Edge Case (Incomplete data)
    it('should render without crashing if details are missing', () => {
        const incompleteData = {
            ticker: 'NODETAILS',
            passes: true,
            details: null // Details are missing
        };
        renderWithProvider(<ScreeningPanel result={incompleteData} loading={false} />);
        // The component should still render the overall result.
        expect(screen.getByText('PASS')).toBeInTheDocument();
        expect(screen.getByText(/Overall Result for NODETAILS/i)).toBeInTheDocument();
    });
});