// frontend-app/src/components/ChartPanel.test.jsx
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChakraProvider } from '@chakra-ui/react';
import ChartPanel from './ChartPanel';

// --- ENHANCED MOCK ---
// Create persistent spies for each series' setData method
const mockCandlestickSetData = vi.fn();
const mockVolumeSetData = vi.fn();
const mockVcpLineSetData = vi.fn();

vi.mock('lightweight-charts', () => ({
    createChart: vi.fn(() => ({
        // Return the specific spies for each series
        addCandlestickSeries: vi.fn(() => ({ setData: mockCandlestickSetData })),
        addHistogramSeries: vi.fn(() => ({ setData: mockVolumeSetData })),
        addLineSeries: vi.fn(() => ({ setData: mockVcpLineSetData })),
        remove: vi.fn(),
        timeScale: () => ({ fitContent: vi.fn() }),
        applyOptions: vi.fn(),
    })),
    ColorType: { Solid: 'solid' },
}));
// --- END ENHANCED MOCK ---

const mockAnalysisData = {
    historicalData: [
        { formatted_date: '2023-01-01', open: 100, high: 102, low: 99, close: 101, volume: 1000 },
        { formatted_date: '2023-01-02', open: 101, high: 103, low: 100, close: 99, volume: 1200 } // a red candle
    ],
    analysis: {
        detected: true,
        message: 'VCP analysis complete.',
        vcpLines: [
            { time: '2023-01-01', value: 102 },
            { time: '2023-01-02', value: 99 }
        ],
    }
};

describe('components/ChartPanel', () => {
    
    beforeEach(() => {
        vi.clearAllMocks();
    });
    
    const renderWithProvider = (ui) => {
        return render(<ChakraProvider>{ui}</ChakraProvider>);
    };

    it('should render the chart container and analysis message with valid data', () => {
        renderWithProvider(<ChartPanel analysisData={mockAnalysisData} />);
        expect(screen.getByRole('heading', { name: /VCP Analysis/i })).toBeInTheDocument();
        expect(screen.getByText('VCP analysis complete.')).toBeInTheDocument();
    });

    it('should render the panel without crashing when data is null', () => {
        renderWithProvider(<ChartPanel analysisData={null} />);
        expect(screen.getByRole('heading', { name: /VCP Analysis/i })).toBeInTheDocument();
    });

    // --- ENHANCED TEST ---
    it('should process and transform data correctly for all chart series', () => {
        renderWithProvider(<ChartPanel analysisData={mockAnalysisData} />);
        
        // Assert Candlestick Series Data
        expect(mockCandlestickSetData).toHaveBeenCalledTimes(1);
        expect(mockCandlestickSetData).toHaveBeenCalledWith([
            { time: '2023-01-01', open: 100, high: 102, low: 99, close: 101 },
            { time: '2023-01-02', open: 101, high: 103, low: 100, close: 99 }
        ]);

        // Assert Volume Series Data (with correct color logic)
        expect(mockVolumeSetData).toHaveBeenCalledTimes(1);
        expect(mockVolumeSetData).toHaveBeenCalledWith([
            { time: '2023-01-01', value: 1000, color: '#26a69a' }, // Green candle (close >= open)
            { time: '2023-01-02', value: 1200, color: '#ef5350' }  // Red candle (close < open)
        ]);

        // Assert VCP Line Series Data
        expect(mockVcpLineSetData).toHaveBeenCalledTimes(1);
        expect(mockVcpLineSetData).toHaveBeenCalledWith(mockAnalysisData.analysis.vcpLines);
    });
});