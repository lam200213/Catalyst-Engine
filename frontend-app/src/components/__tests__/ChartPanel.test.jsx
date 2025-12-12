// frontend-app/src/components/ChartPanel.test.jsx
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import '@testing-library/jest-dom';

import ChartPanel from '../ChartPanel';

const createChartMock = vi.fn();
const addLineSeriesMock = vi.fn();

// Mock lightweight-charts (must include applyOptions on series)
vi.mock('lightweight-charts', () => ({
  createChart: (...args) => createChartMock(...args),
  ColorType: { Solid: 'solid' },
  LineStyle: { Solid: 0, Dashed: 1, Dotted: 2 },
}));

let mockChart;
let mockCandlestick;
let mockVolumeSeries;
let lineSeriesMocks;

beforeEach(() => {
  lineSeriesMocks = [];

  mockCandlestick = {
    setData: vi.fn(),
    createPriceLine: vi.fn(),
    setMarkers: vi.fn(),
  };

  mockVolumeSeries = {
    setData: vi.fn(),
    createPriceLine: vi.fn(),
  };

  addLineSeriesMock.mockImplementation((options) => {
    const series = { setData: vi.fn(), applyOptions: vi.fn(), __options: options };
    lineSeriesMocks.push(series);
    return series;
  });

  mockChart = {
    addCandlestickSeries: vi.fn(() => mockCandlestick),
    addHistogramSeries: vi.fn(() => mockVolumeSeries),
    addLineSeries: addLineSeriesMock,
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
    applyOptions: vi.fn(),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    remove: vi.fn(),
  };

  createChartMock.mockReturnValue(mockChart);
});

const renderWithProvider = (component) =>
  render(<ChakraProvider>{component}</ChakraProvider>);

describe('components/ChartPanel', () => {
  it('1. Business Logic: should display a loading spinner when loading is true', () => {
    renderWithProvider(<ChartPanel analysisData={null} loading={true} />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('2. Edge Case: should render correctly without crashing when analysisData is null', () => {
    renderWithProvider(<ChartPanel analysisData={null} loading={false} />);
    expect(screen.getByText('VCP Analysis')).toBeInTheDocument();
  });

  it('3. Business Logic: should process and pass data to all chart series correctly', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      analysis: { message: 'VCP analysis complete.' },
      chart_data: {
        historicalData: [
          {
            formatted_date: '2023-01-01',
            open: 100,
            high: 102,
            low: 99,
            close: 101,
            volume: 10000,
          },
        ],
        vcpContractions: [],
        vcp_pass: true,
        ma20: [{ time: '2023-01-01', value: 100 }],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [],
        sellPoints: [],
        lowVolumePivotDate: null,
      },
    };

    renderWithProvider(
      <ChartPanel analysisData={mockFullAnalysisData} loading={false} />,
    );

    await waitFor(() => {
      expect(mockCandlestick.setData).toHaveBeenCalledWith([
        { time: '2023-01-01', open: 100, high: 102, low: 99, close: 101 },
      ]);
      expect(mockVolumeSeries.setData).toHaveBeenCalled();
    });
  });

  it('4. Business Logic: should create pivot and stop loss price lines', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      analysis: { message: 'VCP analysis complete.' },
      chart_data: {
        historicalData: [
          {
            formatted_date: '2023-01-01',
            open: 100,
            high: 102,
            low: 99,
            close: 101,
            volume: 10000,
          },
        ],
        vcpContractions: [],
        vcp_pass: true,
        ma20: [],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [],
        pivotPrice: 105,
        sellPoints: [{ value: 95 }],
        lowVolumePivotDate: null,
      },
    };

    renderWithProvider(
      <ChartPanel analysisData={mockFullAnalysisData} loading={false} />,
    );

    await waitFor(() => {
      const calls = mockCandlestick.createPriceLine.mock.calls.map((c) => c[0]);
      const hasPivot = calls.some(
        (arg) => arg?.title === 'Pivot' && arg?.price === 105,
      );
      const hasStopLoss = calls.some(
        (arg) => arg?.title === 'Stop Loss' && arg?.price === 95,
      );
      expect(hasPivot).toBe(true);
      expect(hasStopLoss).toBe(true);
    });
  });

  it('5. Blind Spot: should not create pivot/stop loss lines if pivotPrice or sellPoints are missing', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      analysis: { message: 'VCP analysis complete.' },
      chart_data: {
        historicalData: [
          {
            formatted_date: '2023-01-01',
            open: 100,
            high: 102,
            low: 99,
            close: 101,
            volume: 10000,
          },
        ],
        vcpContractions: [],
        vcp_pass: true,
        ma20: [],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [],
        sellPoints: [],
        lowVolumePivotDate: null,
      },
    };

    renderWithProvider(
      <ChartPanel analysisData={mockFullAnalysisData} loading={false} />,
    );

    await waitFor(() => {
      const calls = mockCandlestick.createPriceLine.mock.calls.map((c) => c[0]);
      const pivotCall = calls.find((arg) => arg?.title === 'Pivot');
      const stopLossCall = calls.find((arg) => arg?.title === 'Stop Loss');
      expect(pivotCall).toBeUndefined();
      expect(stopLossCall).toBeUndefined();
    });
  });

  it('should add a pivot marker to the chart when lowVolumePivotDate is provided', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      analysis: { message: 'VCP analysis complete.' },
      chart_data: {
        historicalData: [
          {
            formatted_date: '2023-01-01',
            open: 100,
            high: 102,
            low: 99,
            close: 101,
            volume: 10000,
          },
        ],
        vcpContractions: [],
        vcp_pass: true,
        ma20: [],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [],
        sellPoints: [],
        lowVolumePivotDate: '2023-01-01',
      },
    };

    renderWithProvider(
      <ChartPanel analysisData={mockFullAnalysisData} loading={false} />,
    );

    await waitFor(() => {
      expect(mockCandlestick.setMarkers).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            time: '2023-01-01',
            text: 'Low Vol',
            position: 'aboveBar',
          }),
        ]),
      );
    });
  });

  it('should clear markers and not add one if lowVolumePivotDate is null', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      analysis: { message: 'VCP analysis complete.' },
      chart_data: {
        historicalData: [
          {
            formatted_date: '2023-01-01',
            open: 100,
            high: 102,
            low: 99,
            close: 101,
            volume: 10000,
          },
        ],
        vcpContractions: [],
        vcp_pass: true,
        ma20: [],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [],
        sellPoints: [],
        lowVolumePivotDate: null,
      },
    };

    renderWithProvider(
      <ChartPanel analysisData={mockFullAnalysisData} loading={false} />,
    );

    await waitFor(() => {
      const args = mockCandlestick.setMarkers.mock.calls.at(-1)?.[0] ?? [];
      expect(args.some((m) => m?.text === 'Low Vol')).toBe(false);
    });
  });

  it('should draw the volume trend line when data is provided', async () => {
    const mockFullAnalysisData = {
      ticker: 'AAPL',
      analysis: { message: 'VCP analysis complete.' },
      chart_data: {
        historicalData: [
          {
            formatted_date: '2023-01-01',
            open: 100,
            high: 102,
            low: 99,
            close: 101,
            volume: 10000,
          },
        ],
        vcpContractions: [],
        vcp_pass: true,
        ma20: [],
        ma50: [],
        ma150: [],
        ma200: [],
        volumeTrendLine: [
          { time: '2023-01-01', value: 500 },
          { time: '2023-01-05', value: 300 },
        ],
        sellPoints: [],
        lowVolumePivotDate: null,
      },
    };

    renderWithProvider(
      <ChartPanel analysisData={mockFullAnalysisData} loading={false} />,
    );

    await waitFor(() => {
      // Volume trend line is the last addLineSeries() call in ChartPanel.jsx (index 8)
      expect(lineSeriesMocks[8].setData).toHaveBeenCalledWith(
        mockFullAnalysisData.chart_data.volumeTrendLine,
      );
    });
  });
});
