// frontend-app/src/App.test.jsx
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ChakraProvider } from '@chakra-ui/react';
import App from './App';

// Mock the lightweight-charts library to prevent canvas errors in JSDOM
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

describe('App Component Integration Test', () => {
  it('should render the main layout with all child components on initial load', () => {
    // 1. Arrange & Act: Render the App component within the ChakraProvider
    render(
      <ChakraProvider>
        <App />
      </ChakraProvider>
    );

    // 2. Assert: Verify each child component is present by querying for its content
    
    // Check for TickerForm by its input placeholder
    expect(screen.getByPlaceholderText(/Enter Ticker/i)).toBeInTheDocument();
    
    // Check for ScreeningPanel by its heading
    expect(screen.getByRole('heading', { name: /Screening Results/i })).toBeInTheDocument();
    
    // Check for ChartPanel by its heading
    expect(screen.getByRole('heading', { name: /VCP Analysis/i })).toBeInTheDocument();
  });
});