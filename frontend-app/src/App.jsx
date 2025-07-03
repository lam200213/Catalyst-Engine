import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { createChart, ColorType } from 'lightweight-charts';
import {
  Box,
  Button,
  Container,
  Flex,
  Heading,
  Input,
  Text,
  VStack,
  Spinner,
  Alert,
  SimpleGrid,
  Tag
} from '@chakra-ui/react';
import './index.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:3000';

function App() {
  const [ticker, setTicker] = useState('AAPL');
  const [screeningResult, setScreeningResult] = useState(null);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const chartContainerRef = useRef();
  const chartRef = useRef(null);

  useEffect(() => {
    // Chart initialization logic remains the same
    if (chartContainerRef.current) {
        if (chartRef.current) {
            chartRef.current.remove();
        }
        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: '#1A202C' },
                textColor: '#E2E8F0',
            },
            width: chartContainerRef.current.clientWidth,
            height: 400,
            grid: {
                vertLines: { color: '#2D3748' },
                horzLines: { color: '#2D3748' },
            },
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
        });
        chartRef.current = chart;

        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#26a69a', downColor: '#ef5350', borderDownColor: '#ef5350',
            borderUpColor: '#26a69a', wickDownColor: '#ef5350', wickUpColor: '#26a69a',
        });

        const volumeSeries = chart.addHistogramSeries({
            color: '#4A5568', priceFormat: { type: 'volume' },
            overlay: true, scaleMargins: { top: 0.8, bottom: 0 },
        });

        const vcpLineSeries = chart.addLineSeries({
            color: '#ECC94B', lineWidth: 2, crosshairMarkerVisible: false,
            lastValueVisible: false, priceLineVisible: false,
        });

        chartRef.current.series = { candlestickSeries, volumeSeries, vcpLineSeries };

        const handleResize = () => chart.applyOptions({ width: chartContainerRef.current.clientWidth });
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            if (chartRef.current) chartRef.current.remove();
        };
    }
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    setScreeningResult(null);
    setAnalysisResult(null);

    // Clear previous chart data
    if (chartRef.current && chartRef.current.series) {
        Object.values(chartRef.current.series).forEach(series => series.setData([]));
    }

    try {
      const screeningRes = await axios.get(`${API_BASE_URL}/screen/${ticker}`);
      setScreeningResult(screeningRes.data);

      const analysisRes = await axios.get(`${API_BASE_URL}/analyze/${ticker}`);
      setAnalysisResult(analysisRes.data.analysis);

      if (analysisRes.data.historicalData && chartRef.current.series) {
        const { t, o, h, l, c, v } = analysisRes.data.historicalData;
        const candlestickData = t.map((time, i) => ({ time, open: o[i], high: h[i], low: l[i], close: c[i] }));
        const volumeData = t.map((time, i) => ({ time, value: v[i], color: c[i] >= o[i] ? '#26a69a' : '#ef5350' }));
        
        chartRef.current.series.candlestickSeries.setData(candlestickData);
        chartRef.current.series.volumeSeries.setData(volumeData);

        if (analysisRes.data.analysis.vcpLines) {
          chartRef.current.series.vcpLineSeries.setData(analysisRes.data.analysis.vcpLines);
        }
      }
    } catch (err) {
      setError(err.response?.data?.error || err.message || "An unknown error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (ticker) fetchData();
  };

  const renderScreeningDetails = () => {
    if (!screeningResult || !screeningResult.details) return null;
    return (
      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4} mt={4}>
        {Object.entries(screeningResult.details).map(([key, value]) => (
          <Flex key={key} justify="space-between" align="center">
            <Text fontSize="sm" color="gray.400">{key.replace(/_/g, ' ')}</Text>
            <Tag colorScheme={value ? 'green' : 'red'} size="sm">
              {value ? 'Pass' : 'Fail'}
            </Tag>
          </Flex>
        ))}
      </SimpleGrid>
    );
  };
  
  return (
    <Container maxW="container.xl" p={4}>
      <VStack spacing={8} align="stretch">
        <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="xl">
          <Heading as="h1" size="xl" color="blue.300" textAlign="center">
            SEPA Stock Screener
          </Heading>
        </Box>

        <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="lg">
          <form onSubmit={handleSubmit}>
            <Flex direction={{ base: 'column', md: 'row' }} gap={4}>
              <Input
                placeholder="Enter Ticker (e.g., AAPL)"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                focusBorderColor="blue.300"
                size="lg"
              />
              <Button
                type="submit"
                colorScheme="blue"
                size="lg"
                isLoading={loading}
                loadingText="Analyzing..."
                w={{ base: '100%', md: 'auto' }}
              >
                Analyze Stock
              </Button>
            </Flex>
          </form>
        </Box>

        {error && (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {error}
          </Alert>
        )}

        <SimpleGrid columns={{ base: 1, lg: 2 }} spacing={8}>
          <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="lg">
            <Heading as="h2" size="lg" mb={4} color="blue.400">Screening Results</Heading>
            {loading && !screeningResult && <Spinner color="blue.300" />}
            {screeningResult && (
              <Box>
                <Text fontSize="md" color="gray.400">Overall Result for {screeningResult.ticker}</Text>
                <Text fontSize="3xl" fontWeight="bold" color={screeningResult.passes ? 'green.300' : 'red.300'}>
                  {screeningResult.passes ? 'PASS' : 'FAIL'}
                </Text>
                {screeningResult.reason && <Text fontSize="sm" color="gray.500" mt={1}>{screeningResult.reason}</Text>}
                {renderScreeningDetails()}
              </Box>
            )}
            {!loading && !screeningResult && <Text color="gray.400">Results will appear here.</Text>}
          </Box>

          <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="lg">
            <Heading as="h2" size="lg" mb={4} color="blue.400">VCP Chart</Heading>
            <Box ref={chartContainerRef} w="100%" h="400px" />
            {analysisResult && (
              <Text mt={2} fontStyle="italic" color="gray.400">
                {analysisResult.message}
              </Text>
            )}
          </Box>
        </SimpleGrid>

        <Box as="footer" textAlign="center" py={4} color="gray.500">
          <Text>&copy; {new Date().getFullYear()} Stock Analysis MVP. All rights reserved.</Text>
        </Box>
      </VStack>
    </Container>
  );
}

export default App;
