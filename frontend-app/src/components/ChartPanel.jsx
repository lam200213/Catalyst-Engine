// frontend-app/src/components/ChartPanel.jsx
import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, LineStyle } from 'lightweight-charts';
import { Box, Text, Heading, Flex, Spinner } from '@chakra-ui/react';

const AnalysisChart = ({ analysisData }) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRef = useRef({}); // To hold all series and price lines

    // Effect for chart initialization
    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: { background: { type: ColorType.Solid, color: '#1A202C' }, textColor: '#E2E8F0' },
            width: chartContainerRef.current.clientWidth,
            height: 500, // Increased height for volume panel
            grid: { vertLines: { color: '#2D3748' }, horzLines: { color: '#2D3748' } },
            timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#4A5568' },
            rightPriceScale: { borderColor: '#4A5568' },
        });
        chartRef.current = chart;

        // --- Create all series upfront ---
        seriesRef.current.candlestickSeries = chart.addCandlestickSeries({
            upColor: '#26a69a', downColor: '#ef5350', borderDownColor: '#ef5350',
            borderUpColor: '#26a69a', wickDownColor: '#ef5350', wickUpColor: '#26a69a',
        });

        seriesRef.current.volumeSeries = chart.addHistogramSeries({
            color: '#4A5568',
            priceFormat: { type: 'volume' },
            priceScaleId: '', // This forces the series to the bottom pane
        });
        // Set pane size for volume
        chart.priceScale('').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

        seriesRef.current.vcpLineSeries = chart.addLineSeries({ color: '#ef5350', lineWidth: 2 });
        seriesRef.current.ma50Series = chart.addLineSeries({ color: 'orange', lineWidth: 1, crosshairMarkerVisible: false });
        seriesRef.current.ma150Series = chart.addLineSeries({ color: 'pink', lineWidth: 1, crosshairMarkerVisible: false });
        seriesRef.current.ma200Series = chart.addLineSeries({ color: 'lightblue', lineWidth: 1, crosshairMarkerVisible: false });

        const handleResize = () => chart.applyOptions({ width: chartContainerRef.current.clientWidth });
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, []);

    // Effect for data updates
    useEffect(() => {
        if (!chartRef.current || !seriesRef.current.candlestickSeries) return;

        // Clear existing data and price lines before adding new ones
        Object.values(seriesRef.current).forEach(series => {
             if (series.setData) series.setData([]); // For series objects
             if (series.remove) series.remove(); // For price line objects
        });
        seriesRef.current.buyPivotLine = null;
        seriesRef.current.stopLossLine = null;

        if (!analysisData?.historicalData || !analysisData?.analysis) {
            return;
        }

        const { historicalData, analysis } = analysisData;
        const { candlestickSeries, volumeSeries, vcpLineSeries, ma50Series, ma150Series, ma200Series } = seriesRef.current;

        // --- Set data for all series ---
        const candlestickData = historicalData.map(d => ({ time: d.formatted_date, open: d.open, high: d.high, low: d.low, close: d.close }));
        const volumeData = historicalData.map(d => ({ time: d.formatted_date, value: d.volume, color: d.close >= d.open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)' }));
        
        candlestickSeries.setData(candlestickData);
        volumeSeries.setData(volumeData);
        vcpLineSeries.setData(analysis.vcpLines || []);
        ma50Series.setData(analysis.ma50 || []);
        ma150Series.setData(analysis.ma150 || []);
        ma200Series.setData(analysis.ma200 || []);

        // --- Create Price Lines for Buy/Sell Points ---
        if (analysis.buyPoints && analysis.buyPoints.length > 0) {
            seriesRef.current.buyPivotLine = candlestickSeries.createPriceLine({
                price: analysis.buyPoints[0].value,
                color: '#4caf50',
                lineWidth: 2,
                lineStyle: LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'Buy Pivot',
            });
        }

        if (analysis.sellPoints && analysis.sellPoints.length > 0) {
            seriesRef.current.stopLossLine = candlestickSeries.createPriceLine({
                price: analysis.sellPoints[0].value,
                color: '#f44336',
                lineWidth: 2,
                lineStyle: LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'Stop Loss',
            });
        }
        
        chartRef.current.timeScale().fitContent();

    }, [analysisData]);

    return (
        <Box>
            <Box ref={chartContainerRef} w="100%" h="500px" />
            {analysisData?.analysis && (
                <Text mt={2} fontStyle="italic" color="gray.400">
                    {analysisData.analysis.message}
                </Text>
            )}
        </Box>
    );
};

const ChartPanel = ({ analysisData, loading }) => {
    return (
        <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="xl" minH="580px">
            <Heading as="h2" size="lg" mb={4} color="blue.400">VCP Analysis</Heading>
            {loading ? (
                <Flex justify="center" align="center" h="500px">
                    <Spinner color="blue.300" size="xl" />
                </Flex>
            ) : (
                <AnalysisChart analysisData={analysisData} />
            )}
        </Box>
    );
};

export default ChartPanel;