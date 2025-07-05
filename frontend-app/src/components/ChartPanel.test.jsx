// frontend-app/src/components/ChartPanel.test.jsx
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChakraProvider } from '@chakra-ui/react';
import ChartPanel from './ChartPanel';

// Enhanced mock for lightweight-charts to spy on methods ---
const mockCandlestick = { setData: vi.fn(), createPriceLine: vi.fn() };
const mockVolume = { setData: vi.fn() };
const mockVcpLine = { setData: vi.fn() };
const mockMa50 = { setData: vi.fn() };
const mockMa150 = { setData: vi.fn() };
const mockMa200 = { setData: vi.fn() };
const mockTimeScale = { fitContent: vi.fn() };

vi.mock('lightweight-charts', () => ({
    createChart: vi.fn(() => ({
        addCandlestickSeries: vi.fn(() => mockCandlestick),
        addHistogramSeries: vi.fn(() => mockVolume),
        addLineSeries: vi.fn((options) => {
            // Return the correct mock based on color for MA lines
            if (options.color === 'orange') return mockMa50;
            if (options.color === 'pink') return mockMa150;
            if (options.color === 'lightblue') return mockMa200;
            return mockVcpLine; // Default for VCP line
        }),
        remove: vi.fn(),
        timeScale: () => mockTimeScale,
        applyOptions: vi.fn(),
        priceScale: () => ({ applyOptions: vi.fn() }),
    })),
    ColorType: { Solid: 'solid' },
    LineStyle: { Dashed: 1 },
}));

// Mock data that includes all fields from the backend
const mockFullAnalysisData = {
    historicalData: [
        { formatted_date: '2023-01-01', open: 100, high: 102, low: 99, close: 101, volume: 1000 },
        { formatted_date: '2023-01-02', open: 101, high: 103, low: 100, close: 99, volume: 1200 }
    ],
    analysis: {
        detected: true,
        message: 'VCP analysis complete.',
        vcpLines: [{ time: '2023-01-01', value: 102 }, { time: '2023-01-02', value: 99 }],
        ma50: [{ time: '2023-01-02', value: 100 }],
        ma150: [{ time: '2023-01-02', value: 98 }],
        ma200: [{ time: '2023-01-02', value: 95 }],
        buyPoints: [{ value: 103.02 }],
        sellPoints: [{ value: 98.01 }],
    }
};

describe('components/ChartPanel', () => {
    
    beforeEach(() => {
        vi.clearAllMocks(); // Reset mocks before each test
    });
    
    const renderWithProvider = (ui) => render(<ChakraProvider>{ui}</ChakraProvider>);

    it('1. Business Logic: should display a loading spinner when loading is true', () => {
        // Gone: Old render call
        // Render the component in a loading state
        renderWithProvider(<ChartPanel analysisData={null} loading={true} />);
        // Gone: expect(screen.getByRole('status')).toBeInTheDocument(); // Chakra spinner has role="status"
        // FIX: Find the spinner by its accessible text content, which is more reliable.
        expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('2. Edge Case: should render correctly without crashing when analysisData is null', () => {
        renderWithProvider(<ChartPanel analysisData={null} loading={false} />);
        expect(screen.getByRole('heading', { name: /VCP Analysis/i })).toBeInTheDocument();
        // Gone: expect(mockCandlestick.setData).not.toHaveBeenCalled();
        // FIX: Assert that the chart clearing logic IS called with an empty array.
        expect(mockCandlestick.setData).toHaveBeenCalledWith([]);
    });

    it('3. Business Logic: should process and pass data to all chart series correctly', () => {
        renderWithProvider(<ChartPanel analysisData={mockFullAnalysisData} loading={false} />);
        
        // Assert Candlestick Series data
        expect(mockCandlestick.setData).toHaveBeenCalledWith([
            { time: '2023-01-01', open: 100, high: 102, low: 99, close: 101 },
            { time: '2023-01-02', open: 101, high: 103, low: 100, close: 99 }
        ]);

        // Assert Volume Series data (with correct color logic)
        expect(mockVolume.setData).toHaveBeenCalledWith([
            { time: '2023-01-01', value: 1000, color: 'rgba(38, 166, 154, 0.5)' }, // Green
            { time: '2023-01-02', value: 1200, color: 'rgba(239, 83, 80, 0.5)' }  // Red
        ]);

        // Assert data for all line series
        expect(mockVcpLine.setData).toHaveBeenCalledWith(mockFullAnalysisData.analysis.vcpLines);
        expect(mockMa50.setData).toHaveBeenCalledWith(mockFullAnalysisData.analysis.ma50);
        expect(mockMa150.setData).toHaveBeenCalledWith(mockFullAnalysisData.analysis.ma150);
        expect(mockMa200.setData).toHaveBeenCalledWith(mockFullAnalysisData.analysis.ma200);
    });

    it('4. Business Logic: should create buy pivot and stop loss price lines', () => {
        renderWithProvider(<ChartPanel analysisData={mockFullAnalysisData} loading={false} />);
        
        expect(mockCandlestick.createPriceLine).toHaveBeenCalledTimes(2);
        
        // Check Buy Pivot line
        expect(mockCandlestick.createPriceLine).toHaveBeenCalledWith({
            price: 103.02,
            color: '#4caf50',
            lineWidth: 2,
            lineStyle: 1, // Dashed
            axisLabelVisible: true,
            title: 'Buy Pivot',
        });

        // Check Stop Loss line
        expect(mockCandlestick.createPriceLine).toHaveBeenCalledWith({
            price: 98.01,
            color: '#f44336',
            lineWidth: 2,
            lineStyle: 1, // Dashed
            axisLabelVisible: true,
            title: 'Stop Loss',
        });
    });

    it('5. Blind Spot: should not create price lines if buyPoints or sellPoints are empty', () => {
        const dataWithoutPivots = {
            ...mockFullAnalysisData,
            analysis: {
                ...mockFullAnalysisData.analysis,
                buyPoints: [],
                sellPoints: []
            }
        };
        renderWithProvider(<ChartPanel analysisData={dataWithoutPivots} loading={false} />);
        expect(mockCandlestick.createPriceLine).not.toHaveBeenCalled();
    });
});