// frontend-app/src/components/ChartPanel.test.jsx
import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChakraProvider } from '@chakra-ui/react';
import ChartPanel from './ChartPanel';

// To capture the crosshair move event handler
let crosshairMoveCallback = null;

// Enhanced mock for lightweight-charts to spy on methods ---
const mockPriceLine = { remove: vi.fn() };
const mockCandlestick = { 
    setData: vi.fn(), 
    createPriceLine: vi.fn(() => mockPriceLine), 
    priceLines: vi.fn(() => [mockPriceLine]), 
    removePriceLine: vi.fn(), 
    setMarkers: vi.fn() 
    };
const mockVolume = { setData: vi.fn() };
const mockVcpLine = { setData: vi.fn() };
const mockMa20 = { setData: vi.fn() };
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
            if (options.color === 'pink') return mockMa20;
            if (options.color === 'red') return mockMa50;
            if (options.color === 'orange') return mockMa150;
            if (options.color === 'green') return mockMa200;
            return mockVcpLine; // Default for VCP line
        }),
        subscribeCrosshairMove: vi.fn((callback) => { crosshairMoveCallback = callback; }),
        unsubscribeCrosshairMove: vi.fn(),
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
    ticker: 'TEST',
    historicalData: [
        { formatted_date: '2023-01-01', open: 100, high: 102, low: 99, close: 101, volume: 1000 }
    ],
    analysis: {
        detected: true,
        message: 'VCP analysis complete.',
        vcpLines: [], ma20: [], ma50: [], ma150: [], ma200: [],
        buyPoints: [{ value: 103.02 }],
        sellPoints: [{ value: 98.01 }],
    }
};


describe('components/ChartPanel', () => {
    
    beforeEach(() => {
        vi.clearAllMocks(); // Reset mocks before each test
        crosshairMoveCallback = null;
    });
    
    const renderWithProvider = (ui) => render(<ChakraProvider>{ui}</ChakraProvider>);

    it('1. Business Logic: should display a loading spinner when loading is true', () => {
        // Render the component in a loading state
        renderWithProvider(<ChartPanel analysisData={null} loading={true} />);
        // Find the spinner by its accessible text content, which is more reliable.
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
        expect(mockCandlestick.setData).toHaveBeenLastCalledWith([
            { time: '2023-01-01', open: 100, high: 102, low: 99, close: 101 }
        ]);

        // Assert Volume Series data (with correct color logic)
        expect(mockVolume.setData).toHaveBeenLastCalledWith([
            { time: '2023-01-01', value: 1000, color: 'rgba(38, 166, 154, 0.5)' }
        ]);

        // Assert data for all line series
        expect(mockVcpLine.setData).toHaveBeenLastCalledWith(mockFullAnalysisData.analysis.vcpLines);
        expect(mockMa20.setData).toHaveBeenLastCalledWith(mockFullAnalysisData.analysis.ma20);
        expect(mockMa50.setData).toHaveBeenLastCalledWith(mockFullAnalysisData.analysis.ma50);
        expect(mockMa150.setData).toHaveBeenLastCalledWith(mockFullAnalysisData.analysis.ma150);
        expect(mockMa200.setData).toHaveBeenLastCalledWith(mockFullAnalysisData.analysis.ma200);
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

    // Render Legend
    it('should render legend with data when crosshair moves over the chart', () => {
        renderWithProvider(<ChartPanel analysisData={mockFullAnalysisData} loading={false} />);
        
        // Arrange: Mock the event data lightweight-charts provides
        const seriesDataMap = new Map();
        seriesDataMap.set(mockCandlestick, { time: '2023-01-01', open: 100, high: 102, low: 99, close: 101 });
        seriesDataMap.set(mockMa50, { value: 99.50 });

        // Act: Manually trigger the captured callback to simulate a crosshair move
        act(() => {
            if (crosshairMoveCallback) {
                crosshairMoveCallback({ time: '2023-01-01', seriesData: seriesDataMap });
            }
        });
        
        // Assert: Check that the legend has rendered with the correct, formatted data
        expect(screen.getByText('TEST')).toBeInTheDocument();
        expect(screen.getByText('H:')).toHaveTextContent('102.00');
        expect(screen.getByText('MA 50:')).toBeInTheDocument();
        expect(screen.getByText('99.50')).toBeInTheDocument();
    });

    it('should clear legend when crosshair leaves chart area', () => {
        renderWithProvider(<ChartPanel analysisData={mockFullAnalysisData} loading={false} />);
        
        // Act 1: Move cursor ONTO the chart to show the legend
        const seriesDataMap = new Map();
        seriesDataMap.set(mockCandlestick, { time: '2023-01-01', open: 100, high: 102, low: 99, close: 101 });
        act(() => {
            if (crosshairMoveCallback) {
                crosshairMoveCallback({ time: '2023-01-01', seriesData: seriesDataMap });
            }
        });
        expect(screen.getByText('TEST')).toBeInTheDocument(); // Verify legend is visible

        // Act 2: Move cursor OFF the chart by sending an invalid event object
        act(() => {
            crosshairMoveCallback({ time: undefined, seriesData: new Map() });
        });

        // Assert: The legend should no longer be in the document
        expect(screen.queryByText('TEST')).not.toBeInTheDocument();
    });

    // Tests for the marker logic
    it('should add a pivot marker to the chart when lowVolumePivotDate is provided', () => {
        // Arrange
        const dataWithPivot = {
            ...mockFullAnalysisData,
            analysis: {
                ...mockFullAnalysisData.analysis,
                lowVolumePivotDate: '2023-01-01',
            },
        };
        renderWithProvider(<ChartPanel analysisData={dataWithPivot} loading={false} />);

        // Assert
        // Check that setMarkers was called with the correct marker object
        expect(mockCandlestick.setMarkers).toHaveBeenCalledWith([
            {
                time: '2023-01-01',
                position: 'belowBar',
                color: '#FFD700',
                shape: 'arrowUp',
                text: 'Low Vol Pivot',
            },
        ]);
    });

    it('should clear markers and not add one if lowVolumePivotDate is null', () => {
        // Arrange: Data without the pivot date (it's null in the base mock)
        renderWithProvider(<ChartPanel analysisData={mockFullAnalysisData} loading={false} />);

        // Assert
        // The setMarkers function should only be called once with an empty array to clear previous markers.
        expect(mockCandlestick.setMarkers).toHaveBeenCalledTimes(1);
        expect(mockCandlestick.setMarkers).toHaveBeenCalledWith([]);
    });

});