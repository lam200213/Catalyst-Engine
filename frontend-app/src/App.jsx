import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { createChart, ColorType } from 'lightweight-charts';
import './App.css';

// The API_BASE_URL points to our API Gateway
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:3000';

function App() {
  const [ticker, setTicker] = useState('AAPL');
  const [screeningResult, setScreeningResult] = useState(null);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const chartContainerRef = useRef();
  const chartRef = useRef(null);
  const candlestickSeriesRef = useRef(null);
  const volumeSeriesRef = useRef(null);
  const vcpLineSeriesRef = useRef(null);

  const colors = {
    backgroundColor: '#1a1a2e',
    lineColor: '#007bff',
    textColor: '#e0e0e0',
    areaTopColor: '#007bff',
    areaBottomColor: 'rgba(0, 123, 255, 0.28)',
  };

  useEffect(() => {
    if (chartContainerRef.current) {
      if (chartRef.current) {
        chartRef.current.remove(); // Clean up existing chart
      }

      const chart = createChart(chartContainerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: colors.backgroundColor },
          textColor: colors.textColor,
        },
        width: chartContainerRef.current.clientWidth,
        height: 400,
        grid: {
          vertLines: { color: '#333' },
          horzLines: { color: '#333' },
        },
        timeScale: {
          timeVisible: true,
          secondsVisible: false,
        },
      });
      chartRef.current = chart;

      candlestickSeriesRef.current = chart.addCandlestickSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderDownColor: '#ef5350',
        borderUpColor: '#26a69a',
        wickDownColor: '#ef5350',
        wickUpColor: '#26a69a',
      });

      volumeSeriesRef.current = chart.addHistogramSeries({
        color: '#888',
        priceFormat: {
          type: 'volume',
        },
        overlay: true,
        scaleMargins: {
          top: 0.8,
          bottom: 0,
        },
      });

      vcpLineSeriesRef.current = chart.addLineSeries({
        color: '#ffc107', // Yellow for VCP lines
        lineWidth: 2,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      });

      const handleResize = () => {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      };

      window.addEventListener('resize', handleResize);

      return () => {
        window.removeEventListener('resize', handleResize);
        if (chartRef.current) {
          chartRef.current.remove();
        }
      };
    }
  }, [colors]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    setScreeningResult(null);
    setAnalysisResult(null);
    candlestickSeriesRef.current.setData([]);
    volumeSeriesRef.current.setData([]);
    vcpLineSeriesRef.current.setData([]);

    try {
      // Call Screening Service
      const screeningRes = await axios.get(`${API_BASE_URL}/screen/${ticker}`);
      setScreeningResult(screeningRes.data);

      // Call Analysis Service 
      const analysisRes = await axios.get(`${API_BASE_URL}/analyze/${ticker}`);
      setAnalysisResult(analysisRes.data.analysis); // Store just the analysis part

      // Prepare chart data
      if (analysisRes.data.historicalData && analysisRes.data.historicalData.c) {
        const { c, o, h, l, v, t } = analysisRes.data.historicalData;
        
        const candlestickData = t.map((time, i) => ({ time, open: o[i], high: h[i], low: l[i], close: c[i] }));
        const volumeData = t.map((time, i) => ({ time, value: v[i], color: c[i] >= o[i] ? '#26a69a' : '#ef5350' }));

        candlestickSeriesRef.current.setData(candlestickData);
        volumeSeriesRef.current.setData(volumeData);

        if (analysisRes.data.analysis.vcpLines) {
          vcpLineSeriesRef.current.setData(analysisRes.data.analysis.vcpLines);
        }
      }

    } catch (err) {
      console.error("Error fetching data:", err);
      setError(err.response?.data?.error || err.message || "An unknown error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    fetchData();
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Stock Analysis MVP</h1>
      </header>

      <main className="app-main">
        <section className="input-section">
          <form onSubmit={handleSubmit} className="ticker-form">
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="Enter Ticker (e.g., AAPL)"
              className="ticker-input"
            />
            <button type="submit" className="analyze-button" disabled={loading}>
              {loading ? 'Analyzing...' : 'Analyze Stock'}
            </button>
          </form>
        </section>

        {error && <div className="error-message">Error: {error}</div>}

        <section className="results-section">
          <div className="screening-results card">
            <h2>Screening Results</h2>
            {screeningResult ? (
              <div>
                <p><strong>Ticker:</strong> {screeningResult.ticker}</p>
                <p><strong>Passes SEPA Criteria:</strong> <span className={screeningResult.passes ? 'pass' : 'fail'}>{screeningResult.passes ? 'YES' : 'NO'}</span></p>
                <p><strong>Reason:</strong> {screeningResult.reason}</p>
                {/* <pre>{JSON.stringify(screeningResult.details, null, 2)}</pre> */}
              </div>
            ) : (
              <p>Enter a ticker and click 'Analyze Stock' to see screening results.</p>
            )}
          </div>

          <div className="chart-section card">
            <h2>Volatility Contraction Pattern (VCP) Chart</h2>
            <div ref={chartContainerRef} className="chart-container"></div>
            {analysisResult && analysisResult.message && (
              <p className="chart-message">{analysisResult.message}</p>
            )}
          </div>
        </section>
      </main>

      <footer className="app-footer">
        <p>&copy; 2024 Stock Analysis MVP. All rights reserved.</p>
      </footer>
    </div>
  );
}

export default App;
