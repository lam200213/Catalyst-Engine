// frontend-app/src/components/ChartPanel.jsx
import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, LineStyle } from 'lightweight-charts';
import { Box, Text, Heading, Flex, Spinner } from '@chakra-ui/react';
import ChartLegend from './ChartLegend';
import { chartColors } from '../theme';

const AnalysisChart = ({ analysisData }) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRef = useRef({}); // To hold all series and price lines
    const [legendData, setLegendData] = useState(null);

    // Effect for chart initialization
    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: { background: { type: ColorType.Solid, color: chartColors.background }, textColor: chartColors.textColor },
            width: chartContainerRef.current.clientWidth,
            height: 500, // Increased height for volume panel
            grid: { vertLines: { color: chartColors.grid }, horzLines: { color: chartColors.grid } },
            timeScale: { timeVisible: true, secondsVisible: false, borderColor: chartColors.grid },
            rightPriceScale: { borderColor: chartColors.grid },
            crosshair: {
                horzLine: { color: chartColors.crosshair.price },
                vertLine: { color: chartColors.crosshair.time }
            },
        });
        chartRef.current = chart;

        // --- Create all series upfront ---
        seriesRef.current.candlestickSeries = chart.addCandlestickSeries({
            upColor: chartColors.candlestick.up, downColor: chartColors.candlestick.down, borderDownColor: chartColors.candlestick.down,
            borderUpColor: chartColors.candlestick.up, wickDownColor: chartColors.candlestick.down, wickUpColor: chartColors.candlestick.up,
        });

        seriesRef.current.volumeSeries = chart.addHistogramSeries({
            color: chartColors.volume.base,
            priceFormat: { type: 'volume' },
            priceScaleId: '', // This forces the series to the bottom pane
        });
        // Set pane size for volume
        chart.priceScale('').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

        seriesRef.current.vcpLineSeries = chart.addLineSeries({ color: chartColors.vcp.line, lineWidth: 2 });
        seriesRef.current.ma20Series = chart.addLineSeries({ color: chartColors.ma.ma20, lineWidth: 1 });
        seriesRef.current.ma50Series = chart.addLineSeries({ color: chartColors.ma.ma50, lineWidth: 1 });
        seriesRef.current.ma150Series = chart.addLineSeries({ color: chartColors.ma.ma150, lineWidth: 1 });
        seriesRef.current.ma200Series = chart.addLineSeries({ color: chartColors.ma.ma200, lineWidth: 1 });

        // Create a line series for the volume trend line on the volume pane
        seriesRef.current.volumeTrendLine = chart.addLineSeries({
            priceScaleId: '', // Attach to the volume pane
            color: chartColors.volume.trendLine,
            lineWidth: 2,
            lineStyle: LineStyle.Dashed,
            crosshairMarkerVisible: false,
        });

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
                    { name: 'MA 20', value: param.seriesData.get(seriesRef.current.ma20Series)?.value, color: chartColors.ma.ma20 },
                    { name: 'MA 50', value: param.seriesData.get(seriesRef.current.ma50Series)?.value, color: chartColors.ma.ma50 },
                    { name: 'MA 150', value: param.seriesData.get(seriesRef.current.ma150Series)?.value, color: chartColors.ma.ma150 },
                    { name: 'MA 200', value: param.seriesData.get(seriesRef.current.ma200Series)?.value, color: chartColors.ma.ma200 },
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
        const { candlestickSeries, volumeSeries, vcpLineSeries, ma20Series, ma50Series, ma150Series, ma200Series, volumeTrendLine } = seriesRef.current;

        // --- Set data for all series ---
        const candlestickData = historicalData.map(d => ({ time: d.formatted_date, open: d.open, high: d.high, low: d.low, close: d.close }));
        const volumeData = historicalData.map(d => ({ time: d.formatted_date, value: d.volume, color: d.close >= d.open ? chartColors.volume.up : chartColors.volume.down }));
        
        candlestickSeries.setData(candlestickData);
        volumeSeries.setData(volumeData);
        vcpLineSeries.setData(analysis.vcpLines || []);
        ma20Series.setData(analysis.ma20 || []);
        ma50Series.setData(analysis.ma50 || []);
        ma150Series.setData(analysis.ma150 || []);
        ma200Series.setData(analysis.ma200 || []);
        volumeTrendLine.setData(analysis.volumeTrendLine || []);

        // Start of Marker Logic
        // Always clear existing markers before adding new ones to prevent duplicates.
        candlestickSeries.setMarkers([]);

        // Check if the lowVolumePivotDate exists in the analysis data.
        if (analysis.lowVolumePivotDate) {
            // Create the marker object with the specified properties.
            const pivotMarker = {
                time: analysis.lowVolumePivotDate,
                position: 'belowBar',
                color: chartColors.pivots.lowVolume,
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
                color: chartColors.pivots.buy,
                lineWidth: 2,
                lineStyle: LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'Buy Pivot',
            });
        }

        if (analysis.sellPoints && analysis.sellPoints.length > 0) {
            seriesRef.current.stopLossLine = candlestickSeries.createPriceLine({
                price: analysis.sellPoints[0].value,
                color: chartColors.pivots.stopLoss,
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