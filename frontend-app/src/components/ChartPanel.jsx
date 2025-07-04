import React, { useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import { Box, Text, Heading, Flex, Spinner } from '@chakra-ui/react';

const AnalysisChart = ({ analysisData }) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: { background: { type: ColorType.Solid, color: '#1A202C' }, textColor: '#E2E8F0' },
            width: chartContainerRef.current.clientWidth,
            height: 400,
            grid: { vertLines: { color: '#2D3748' }, horzLines: { color: '#2D3748' } },
            timeScale: { timeVisible: true, secondsVisible: false },
        });
        chartRef.current = chart;

        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#26a69a', downColor: '#ef5350', borderDownColor: '#ef5350',
            borderUpColor: '#26a69a', wickDownColor: '#ef5350', wickUpColor: '#26a69a',
        });

        const volumeSeries = chart.addHistogramSeries({
            color: '#4A5568',
            priceFormat: { type: 'volume' },
            // overlay: true is removed to place volume in a separate panel
            // scaleMargins can be adjusted or removed for default behavior
            scaleMargins: { top: 0.85, bottom: 0 }, // Adjust top margin to give it more space
        });

        const vcpLineSeries = chart.addLineSeries({
            color: '#ECC94B', lineWidth: 2,
        });

        chartRef.current.series = { candlestickSeries, volumeSeries, vcpLineSeries };

        const handleResize = () => chart.applyOptions({ width: chartContainerRef.current.clientWidth });
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, []);

    useEffect(() => {
        if (!chartRef.current || !chartRef.current.series || !analysisData?.historicalData) {
            if (chartRef.current?.series) {
                 Object.values(chartRef.current.series).forEach(series => series.setData([]));
            }
            return;
        }

        const { historicalData, analysis } = analysisData;
        const candlestickData = historicalData.map(d => ({ time: d.formatted_date, open: d.open, high: d.high, low: d.low, close: d.close }));
        const volumeData = historicalData.map(d => ({ time: d.formatted_date, value: d.volume, color: d.close >= d.open ? '#26a69a' : '#ef5350' }));

        chartRef.current.series.candlestickSeries.setData(candlestickData);
        chartRef.current.series.volumeSeries.setData(volumeData);
        chartRef.current.series.vcpLineSeries.setData(analysis.vcpLines || []);

        chartRef.current.timeScale().fitContent();

    }, [analysisData]);

    return (
        <Box>
            <Box ref={chartContainerRef} w="100%" h="400px" />
            {analysisData?.analysis && (
                <Text mt={2} fontStyle="italic" color="gray.400">
                    {analysisData.analysis.message}
                </Text>
            )}
        </Box>
    );
};

const ChartPanel = ({ analysisData, loading }) => {
    // Add conditional rendering logic inside the return statement
    return (
        <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="xl">
            <Heading as="h2" size="lg" mb={4} color="blue.400">VCP Analysis</Heading>
            {loading ? (
                <Flex justify="center" align="center" h="400px">
                    <Spinner color="blue.300" />
                </Flex>
            ) : (
                <AnalysisChart analysisData={analysisData} />
            )}
        </Box>
    );
};

export default ChartPanel;