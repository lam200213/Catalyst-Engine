import React from 'react';
import { screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { renderWithProviders } from '../../test-utils'; 
import ChartLegend from '../ChartLegend';

// Mock data for testing all scenarios
const mockLegendData = {
    ohlcv: {
        time: '2025-07-05',
        open: 150.25,
        high: 155.75,
        low: 149.50,
        close: 155.00,
        volume: 1534000
    },
    mas: [
        { name: 'MA 50', value: 152.50, color: 'orange' },
        { name: 'MA 150', value: 148.75, color: 'pink' },
        { name: 'MA 200', value: undefined, color: 'lightblue' } // Edge case: one MA has no data for this point
    ]
};

describe('components/ChartLegend', () => {
    it('1. Business Logic: should render all data correctly when props are valid', () => {
        renderWithProviders(<ChartLegend ticker="AAPL" legendData={mockLegendData} />);

        // Assert Ticker and Date are rendered
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('2025-07-05')).toBeInTheDocument();

        // Assert OHLC values are correctly formatted and displayed
        expect(screen.getByText('O:')).toHaveTextContent('O: 150.25');
        expect(screen.getByText('H:')).toHaveTextContent('H: 155.75');
        expect(screen.getByText('L:')).toHaveTextContent('L: 149.50');
        expect(screen.getByText('C:')).toHaveTextContent('C: 155.00');

        // Assert that valid MAs are displayed
        expect(screen.getByText('MA 50:')).toBeInTheDocument();
        expect(screen.getByText('152.50')).toBeInTheDocument();

        // Assert that volume is displayed and correctly formatted
        expect(screen.getByText('Volume:')).toBeInTheDocument();
        expect(screen.getByText('1.53M')).toBeInTheDocument();
    });

    // Test for zero/null volume edge cases
    it('2. Edge Case: should handle zero or null volume correctly', () => {
        const dataWithZeroVol = { ...mockLegendData, ohlcv: { ...mockLegendData.ohlcv, volume: 0 } };
        const { rerender } = renderWithProviders(<ChartLegend ticker="AAPL" legendData={dataWithZeroVol} />);
  
          // Assert that the text '0' is rendered in the document.
        expect(screen.getByText('0')).toBeInTheDocument();
      
        const dataWithNullVol = { ...mockLegendData, ohlcv: { ...mockLegendData.ohlcv, volume: null } };
        rerender(<ChartLegend ticker="AAPL" legendData={dataWithNullVol} />);
        // Assert that the text 'N/A' is rendered in the document.
        expect(screen.getByText('N/A')).toBeInTheDocument();
    });


    it('2. Edge Case: should not render if legendData is null', () => {
        renderWithProviders(<ChartLegend ticker="AAPL" legendData={null} />);
        // Assert that content specific to the component is not present.
        expect(screen.queryByText('AAPL')).not.toBeInTheDocument();
    });

    it('2. Edge Case: should gracefully omit an MA if its value is undefined', () => {
        renderWithProviders(<ChartLegend ticker="AAPL" legendData={mockLegendData} />);
        expect(screen.getByText('MA 150:')).toBeInTheDocument(); // This one should be present
        expect(screen.queryByText('MA 200:')).not.toBeInTheDocument(); // This one should be absent
    });

    it('3. Security: should escape and render malicious ticker string as plain text', () => {
        const maliciousTicker = '<script>alert("XSS")</script>';
        renderWithProviders(<ChartLegend ticker={maliciousTicker} legendData={mockLegendData} />);
        // The malicious string should be rendered as text content, not as HTML
        expect(screen.getByText(maliciousTicker)).toBeInTheDocument();
    });
});