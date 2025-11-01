// frontend-app/src/components/ChartPanel.test.jsx
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ChartPanel from './ChartPanel';
import { ChakraProvider } from '@chakra-ui/react';
import '@testing-library/jest-dom';

// Mock lightweight-charts
vi.mock('lightweight-charts', () => ({
  createChart: vi.fn(() => ({
    addCandlestickSeries: vi.fn(() => mockCandlestick),
    addHistogramSeries: vi.fn(() => mockVolumeSeries),
    addLineSeries: vi.fn((options) => {
      // Return different mock based on call order/options
      if (currentLineSeriesCallCount === 0) {
        currentLineSeriesCallCount++;
        return mockLineSeries;
      }
      return mockVolumeTrendLine;
    }),
    priceScale: vi.fn(() => ({
      applyOptions: vi.fn(),
    })),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
    applyOptions: vi.fn(),
    timeScale: vi.fn(() => ({
      fitContent: vi.fn(),
    })),
    remove: vi.fn(),
  })),
  ColorType: { Solid: 'solid' },
  LineStyle: { Dashed: 'dashed', Dotted: 'dotted' },
}));

let mockCandlestick, mockVolumeSeries, mockLineSeries, mockVolumeTrendLine, currentLineSeriesCallCount;

beforeEach(() => {
  currentLineSeriesCallCount = 0;

  mockCandlestick = {
    setData: vi.fn(),
    createPriceLine: vi.fn(),
    setMarkers: vi.fn(),
    priceLines: vi.fn(() => []),
  };
  
  mockVolumeSeries = {
    setData: vi.fn(),
    createPriceLine: vi.fn(),
    priceLines: vi.fn(() => []),
  };
  
  mockLineSeries = {
    setData: vi.fn(),
  };
  
  mockVolumeTrendLine = {
    setData: vi.fn(),
  };
});

const renderWithProvider = (component) => {
  return render(<ChakraProvider>{component}</ChakraProvider>);
};

describe('components/ChartPanel', () => {
  it('1. Business Logic: should display a loading spinner when loading is true', () => {
    renderWithProvider(<ChartPanel analysisData={null} loading={true} />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });


  it('2. Edge Case: should render correctly without crashing when analysisData is null', () => {
    renderWithProvider(<ChartPanel analysisData={null} loading={false} />);
    expect(screen.getByText('VCP Analysis')).toBeInTheDocument();
  });

  // Fixed test - updated mock data structure
  it('3. Business Logic: should process and pass data to all chart series correctly', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      // Changed from analysisData.analysis to analysisData.chart_data
      chart_data: {
        historicalData: [
          { formatted_date: '2023-01-01', open: 100, high: 102, low: 99, close: 101, volume: 10000 }
        ],
        vcpLines: [],
        ma20: [{ time: '2023-01-01', value: 100 }],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [],
        buyPoints: [],
        sellPoints: [],
        lowVolumePivotDate: null,
      },
    };

    renderWithProvider(<ChartPanel analysisData={mockFullAnalysisData} loading={false} />);
    
    await waitFor(() => {
      expect(mockCandlestick.setData).toHaveBeenCalledWith([
        { time: '2023-01-01', open: 100, high: 102, low: 99, close: 101 }
      ]);
    });
  });

  // Fixed test with correct data structure
  it('4. Business Logic: should create buy pivot and stop loss price lines', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      chart_data: {
        historicalData: [
          { formatted_date: '2023-01-01', open: 100, high: 102, low: 99, close: 101, volume: 10000 }
        ],
        vcpLines: [],
        ma20: [],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [],
        buyPoints: [{ value: 105 }],
        sellPoints: [{ value: 95 }],
        lowVolumePivotDate: null,
      },
    };

    renderWithProvider(<ChartPanel analysisData={mockFullAnalysisData} loading={false} />);
    
    await waitFor(() => {
      // Changed from 4 to 2 (only buy pivot and stop loss)
      expect(mockCandlestick.createPriceLine).toHaveBeenCalledTimes(2);
    }, { timeout: 2000 });
    
    expect(mockCandlestick.createPriceLine).toHaveBeenCalledWith(
      expect.objectContaining({
        price: 105,
        title: 'Buy Pivot',
      })
    );
    
    expect(mockCandlestick.createPriceLine).toHaveBeenCalledWith(
      expect.objectContaining({
        price: 95,
        title: 'Stop Loss',
      })
    );
  });

  it('5. Blind Spot: should not create price lines if buyPoints or sellPoints are empty', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      chart_data: {
        historicalData: [
          { formatted_date: '2023-01-01', open: 100, high: 102, low: 99, close: 101, volume: 10000 }
        ],
        vcpLines: [],
        ma20: [],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [],
        buyPoints: [],
        sellPoints: [],
        lowVolumePivotDate: null,
      },
    };

    renderWithProvider(<ChartPanel analysisData={mockFullAnalysisData} loading={false} />);
    
    await waitFor(() => {
      const calls = mockCandlestick.createPriceLine.mock.calls;
      const buyPivotCall = calls.find(call => call[0].title === 'Buy Pivot');
      const stopLossCall = calls.find(call => call[0].title === 'Stop Loss');
      
      expect(buyPivotCall).toBeUndefined();
      expect(stopLossCall).toBeUndefined();
    });
  });

  // Fixed marker test
  it('should add a pivot marker to the chart when lowVolumePivotDate is provided', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      chart_data: {
        historicalData: [
          { formatted_date: '2023-01-01', open: 100, high: 102, low: 99, close: 101, volume: 10000 }
        ],
        vcpLines: [],
        ma20: [],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [],
        buyPoints: [],
        sellPoints: [],
        lowVolumePivotDate: '2023-01-01',
      },
    };

    renderWithProvider(<ChartPanel analysisData={mockFullAnalysisData} loading={false} />);
    
    await waitFor(() => {
      expect(mockCandlestick.setMarkers).toHaveBeenCalledWith([
        {
          time: '2023-01-01',
          position: 'belowBar',
          color: expect.any(String),
          shape: 'arrowUp',
          text: 'Low Vol Pivot',
        },
      ]);
    });
  });

  it('should clear markers and not add one if lowVolumePivotDate is null', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      chart_data: {
        historicalData: [
          { formatted_date: '2023-01-01', open: 100, high: 102, low: 99, close: 101, volume: 10000 }
        ],
        vcpLines: [],
        ma20: [],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [],
        buyPoints: [],
        sellPoints: [],
        lowVolumePivotDate: null,
      },
    };

    renderWithProvider(<ChartPanel analysisData={mockFullAnalysisData} loading={false} />);
    
    await waitFor(() => {
      expect(mockCandlestick.setMarkers).toHaveBeenCalledWith([]);
    });
  });

  it('should draw the volume trend line when data is provided', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      chart_data: {
        historicalData: [
          { formatted_date: '2023-01-01', open: 100, high: 102, low: 99, close: 101, volume: 10000 }
        ],
        vcpLines: [],
        ma20: [],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [
          { time: '2023-01-01', value: 500 },
          { time: '2023-01-05', value: 300 },
        ],
        buyPoints: [],
        sellPoints: [],
        lowVolumePivotDate: null,
      },
    };

    renderWithProvider(<ChartPanel analysisData={mockFullAnalysisData} loading={false} />);
    
    await waitFor(() => {
      expect(mockVolumeTrendLine.setData).toHaveBeenCalled();
    }, { timeout: 2000 });
    
    expect(mockVolumeTrendLine.setData).toHaveBeenCalledWith(
      mockFullAnalysisData.chart_data.volumeTrendLine
    );
  });
});