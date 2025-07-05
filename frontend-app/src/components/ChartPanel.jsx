// frontend-app/src/components/ChartPanel.jsx
import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, LineStyle } from 'lightweight-charts';
import { Box, Text, Heading, Flex, Spinner } from '@chakra-ui/react';
import ChartLegend from './ChartLegend';

const AnalysisChart = ({ analysisData }) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRef = useRef({}); // To hold all series and price lines
    const [legendData, setLegendData] = useState(null);

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
        seriesRef.current.ma20Series = chart.addLineSeries({ color: 'pink', lineWidth: 1 });
        seriesRef.current.ma50Series = chart.addLineSeries({ color: 'red', lineWidth: 1 });
        seriesRef.current.ma150Series = chart.addLineSeries({ color: 'orange', lineWidth: 1 });
        seriesRef.current.ma200Series = chart.addLineSeries({ color: 'green', lineWidth: 1 });

        // Event handling logic for legend
        const handleCrosshairMove = (param) => {
            if (!param.time || !param.seriesData.size) {
                setLegendData(null);
                return;
            }
            const ohlcv = param.seriesData.get(seriesRef.current.candlestickSeries);
            const volume = param.seriesData.get(seriesRef.current.volumeSeries);
            
            setLegendData({
                ticker: analysisData?.ticker,
                ohlcv: { ...ohlcv, time: param.time, volume: volume?.value },
                mas: [
                    { name: 'MA 20', value: param.seriesData.get(seriesRef.current.ma20Series)?.value, color: 'pink' },
                    { name: 'MA 50', value: param.seriesData.get(seriesRef.current.ma50Series)?.value, color: 'red' },
                    { name: 'MA 150', value: param.seriesData.get(seriesRef.current.ma150Series)?.value, color: 'orange' },
                    { name: 'MA 200', value: param.seriesData.get(seriesRef.current.ma200Series)?.value, color: 'green' },
                ],
            });
        };

        chart.subscribeCrosshairMove(handleCrosshairMove);

        const handleResize = () => chart.applyOptions({ width: chartContainerRef.current.clientWidth });
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.unsubscribeCrosshairMove(handleCrosshairMove);
            chart.remove();
        };
    }, [analysisData?.ticker]); // Add ticker to dependency array to update legend


    // Effect for data updates
    useEffect(() => {
        if (!chartRef.current || !seriesRef.current.candlestickSeries) return;

        // --- Clear data for all series ---
        Object.values(seriesRef.current).forEach(series => {
            if (series && typeof series.setData === 'function') {
                series.setData([]);
            }
        });
        if (seriesRef.current.candlestickSeries && seriesRef.current.candlestickSeries.priceLines) {
            seriesRef.current.candlestickSeries.priceLines().forEach(line => seriesRef.current.candlestickSeries.removePriceLine(line));
        }

        if (!analysisData?.historicalData || !analysisData?.analysis) {
            // Clear markers if there is no data
            seriesRef.current.candlestickSeries.setMarkers([]);
            return;
        }

        const { historicalData, analysis } = analysisData;
        const { candlestickSeries, volumeSeries, vcpLineSeries, ma20Series, ma50Series, ma150Series, ma200Series } = seriesRef.current;

        // --- Set data for all series ---
        const candlestickData = historicalData.map(d => ({ time: d.formatted_date, open: d.open, high: d.high, low: d.low, close: d.close }));
        const volumeData = historicalData.map(d => ({ time: d.formatted_date, value: d.volume, color: d.close >= d.open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)' }));
        
        candlestickSeries.setData(candlestickData);
        volumeSeries.setData(volumeData);
        vcpLineSeries.setData(analysis.vcpLines || []);
        ma20Series.setData(analysis.ma20 || []);
        ma50Series.setData(analysis.ma50 || []);
        ma150Series.setData(analysis.ma150 || []);
        ma200Series.setData(analysis.ma200 || []);

        // Start of Marker Logic
        // Always clear existing markers before adding new ones to prevent duplicates.
        candlestickSeries.setMarkers([]);

        // Check if the lowVolumePivotDate exists in the analysis data.
        if (analysis.lowVolumePivotDate) {
            // Create the marker object with the specified properties.
            const pivotMarker = {
                time: analysis.lowVolumePivotDate,
                position: 'belowBar',
                color: '#FFD700', // A distinct yellow color
                shape: 'arrowUp',
                text: 'Low Vol Pivot'
            };
            // Set the marker on the candlestick series. setMarkers expects an array.
            candlestickSeries.setMarkers([pivotMarker]);
        }
        // End of Marker Logic

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
        // Add position relative to contain the absolutely positioned legend
        <Box position="relative">
            <ChartLegend ticker={analysisData?.ticker} legendData={legendData} />
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