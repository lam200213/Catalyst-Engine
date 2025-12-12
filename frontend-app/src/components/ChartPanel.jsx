// frontend-app/src/components/ChartPanel.jsx
import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, LineStyle } from 'lightweight-charts';
import { 
    Box, Text, Heading, Flex, Spinner, HStack, Badge, IconButton, Tooltip,
    Menu, MenuButton, MenuList, MenuOptionGroup, MenuItemOption, MenuDivider 
} from '@chakra-ui/react';
import { Maximize2, Minimize2, Activity, Footprints, Layers } from 'lucide-react';
import ChartLegend from './ChartLegend';
import { chartColors } from '../theme';

const AnalysisChart = ({ analysisData, isFullScreen, visibleLayers }) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRef = useRef({}); 
    const [legendData, setLegendData] = useState(null);

    // Consolidated Effect: Init Chart + Paint Data
    useEffect(() => {
        if (!chartContainerRef.current) return;

        // 1. Initialize Chart
        const chart = createChart(chartContainerRef.current, {
            layout: { background: { type: ColorType.Solid, color: chartColors.background }, textColor: chartColors.textColor },
            width: chartContainerRef.current.clientWidth,
            height: isFullScreen ? window.innerHeight - 100 : 500,
            grid: { vertLines: { color: chartColors.grid }, horzLines: { color: chartColors.grid } },
            timeScale: { timeVisible: true, secondsVisible: false, borderColor: chartColors.grid },
            rightPriceScale: { borderColor: chartColors.grid },
            crosshair: {
                horzLine: { color: chartColors.crosshair.price },
                vertLine: { color: chartColors.crosshair.time }
            },
        });
        chartRef.current = chart;

        // 2. Initialize Series
        const candlestickSeries = chart.addCandlestickSeries({
            upColor: chartColors.candlestick.up, 
            downColor: chartColors.candlestick.down, 
            borderDownColor: chartColors.candlestick.down,
            borderUpColor: chartColors.candlestick.up, 
            wickDownColor: chartColors.candlestick.down, 
            wickUpColor: chartColors.candlestick.up,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        const volumeSeries = chart.addHistogramSeries({
            color: chartColors.volume.base,
            priceFormat: { type: 'volume' },
            priceScaleId: '', 
            lastValueVisible: false,
            priceLineVisible: false,
        });
        chart.priceScale('').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

        // VCP Zigzag uses dynamic color based on pass/fail in the Paint Logic
        const vcpZigzagSeries = chart.addLineSeries({
             color: '#3182CE', lineWidth: 2, lineStyle: LineStyle.Solid,
             lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
        });

        const vcpUpperBracketSeries = chart.addLineSeries({
             color: '#A0AEC0', lineWidth: 1, lineStyle: LineStyle.Dashed, 
             lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
        });

        const vcpLowerBracketSeries = chart.addLineSeries({
             color: '#A0AEC0', lineWidth: 1, lineStyle: LineStyle.Dashed, 
             lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
        });

        const resistanceLineSeries = chart.addLineSeries({
             color: '#718096', lineWidth: 1, lineStyle: LineStyle.Dotted,
             lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
        });

        // Initialize MAs (Visibility controlled by separate effect)
        const ma20Series = chart.addLineSeries({ color: chartColors.ma.ma20, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        const ma50Series = chart.addLineSeries({ color: chartColors.ma.ma50, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        const ma150Series = chart.addLineSeries({ color: chartColors.ma.ma150, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        const ma200Series = chart.addLineSeries({ color: chartColors.ma.ma200, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        
        const volumeTrendLine = chart.addLineSeries({ priceScaleId: '', color: chartColors.volume.trendLine, lineWidth: 2, lineStyle: LineStyle.Dashed, crosshairMarkerVisible: false });

        // Store refs
        seriesRef.current = {
            candlestickSeries, volumeSeries, vcpZigzagSeries, vcpUpperBracketSeries, 
            vcpLowerBracketSeries, resistanceLineSeries, ma20Series, ma50Series, 
            ma150Series, ma200Series, volumeTrendLine
        };

        // 3. Data Processing & Painting
        const paintChart = () => {
            const analysis = analysisData?.chart_data;
            const historicalData = analysis?.historicalData;

            if (!historicalData || !analysis) return;

            // Visual feedback for failure
            // If explicit vcp_pass is false, style the zigzag as orange/warning
            if (analysis.vcp_pass === false) {
                vcpZigzagSeries.applyOptions({ color: '#ED8936', lineWidth: 2 }); // Orange
            } else {
                vcpZigzagSeries.applyOptions({ color: '#3182CE', lineWidth: 2 }); // Blue
            }

            const candlestickData = historicalData.map(d => ({ time: d.formatted_date, open: d.open, high: d.high, low: d.low, close: d.close }));
            const volumeData = historicalData.map(d => ({ time: d.formatted_date, value: d.volume, color: d.close >= d.open ? chartColors.volume.up : chartColors.volume.down }));
            
            candlestickSeries.setData(candlestickData);
            volumeSeries.setData(volumeData);
            ma20Series.setData(analysis.ma20 || []);
            ma50Series.setData(analysis.ma50 || []);
            ma150Series.setData(analysis.ma150 || []);
            ma200Series.setData(analysis.ma200 || []);
            volumeTrendLine.setData(analysis.volumeTrendLine || []);

            // VCP Logic
            const contractions = analysis.vcpContractions || [];
            const markers = [];
            const zigzagData = [];    
            const resistanceData = []; 
            const upperBracketData = []; 
            const lowerBracketData = []; 
            const UPPER_OFFSET = 1.0025;
            const LOWER_OFFSET = 0.9975;
            const BRACKET_COLOR = '#A0AEC0';

            contractions.forEach((c) => {
                const peak = c.start_price;
                const trough = c.end_price;

                zigzagData.push({ time: c.start_date, value: peak });
                zigzagData.push({ time: c.end_date, value: trough });
                resistanceData.push({ time: c.start_date, value: peak });

                upperBracketData.push({ time: c.start_date, value: peak * UPPER_OFFSET, color: BRACKET_COLOR });
                upperBracketData.push({ time: c.end_date, value: peak * UPPER_OFFSET, color: 'transparent' });

                lowerBracketData.push({ time: c.start_date, value: trough * LOWER_OFFSET, color: BRACKET_COLOR });
                lowerBracketData.push({ time: c.end_date, value: trough * LOWER_OFFSET, color: 'transparent' });

                markers.push({
                    time: c.end_date, position: 'belowBar', color: '#E53E3E', 
                    shape: 'arrowUp', text: `-${(c.depth_percent * 100).toFixed(1)}%`, size: 0, 
                });
            });

            const safeSort = (a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0);
            const deduplicateData = (data) => {
                if (!data || data.length === 0) return [];
                const sorted = [...data].sort(safeSort);
                const unique = [];
                let lastTime = null;
                for (const item of sorted) {
                    if (item.time !== lastTime) { unique.push(item); lastTime = item.time; } 
                    else { unique[unique.length - 1] = item; }
                }
                return unique;
            };

            vcpZigzagSeries.setData(deduplicateData(zigzagData));
            vcpUpperBracketSeries.setData(deduplicateData(upperBracketData));
            vcpLowerBracketSeries.setData(deduplicateData(lowerBracketData));
            resistanceLineSeries.setData(deduplicateData(resistanceData));

            if (analysis.lowVolumePivotDate) {
                markers.push({
                    time: analysis.lowVolumePivotDate, position: 'aboveBar', color: chartColors.pivots.lowVolume,
                    shape: 'arrowDown', text: 'Low Vol'
                });
            }
            markers.sort(safeSort);
            candlestickSeries.setMarkers(markers);

            // --- Condition Price Lines on 'priceLines' layer ---
            if (visibleLayers.includes('priceLines')) {
                // Pivot Price (Solid)
                if (analysis.pivotPrice) {
                    candlestickSeries.createPriceLine({
                        price: analysis.pivotPrice, color: chartColors.pivots?.buy || '#48BB78',
                        lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: 'Pivot',
                    });
                }
                // Stop Loss (Dashed)
                if (analysis.sellPoints && analysis.sellPoints.length > 0) {
                    candlestickSeries.createPriceLine({
                        price: analysis.sellPoints[0].value, color: chartColors.pivots.stopLoss,
                        lineWidth: 2, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'Stop Loss',  
                    });
                }
                // Last Close / Vol (Dotted)
                if (historicalData && historicalData.length > 0) {
                    const lastDataPoint = historicalData[historicalData.length - 1];
                    candlestickSeries.createPriceLine({
                        price: lastDataPoint.close,
                        color: chartColors.textColor,
                        lineWidth: 1,
                        lineStyle: LineStyle.Dotted,
                        axisLabelVisible: true,
                        title: 'Last Close',
                    });
                     volumeSeries.createPriceLine({
                        price: lastDataPoint.volume,
                        color: chartColors.textColor,
                        lineWidth: 1,
                        lineStyle: LineStyle.Dotted,
                        axisLabelVisible: true,
                        title: 'Last Vol',
                    });
                }
            }
        };

        // 4. Paint Data
        paintChart();
        chart.timeScale().fitContent();

        // 5. Handlers
        const handleCrosshairMove = (param) => {
            if (!param.time || !param.seriesData.size) { setLegendData(null); return; }
            const ohlcv = param.seriesData.get(candlestickSeries);
            const volume = param.seriesData.get(volumeSeries);
            setLegendData({
                ticker: analysisData?.ticker,
                ohlcv: { ...ohlcv, time: param.time, volume: volume?.value },
                mas: [
                    { name: 'MA 20', value: param.seriesData.get(ma20Series)?.value, color: chartColors.ma.ma20 },
                    { name: 'MA 50', value: param.seriesData.get(ma50Series)?.value, color: chartColors.ma.ma50 },
                    { name: 'MA 150', value: param.seriesData.get(ma150Series)?.value, color: chartColors.ma.ma150 },
                    { name: 'MA 200', value: param.seriesData.get(ma200Series)?.value, color: chartColors.ma.ma200 },
                ],
            });
        };
        chart.subscribeCrosshairMove(handleCrosshairMove);

        const handleResize = () => {
             if (chartContainerRef.current) {
                chart.applyOptions({ 
                    width: chartContainerRef.current.clientWidth,
                    height: isFullScreen ? window.innerHeight - 100 : 500
                });
             }
        };
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.unsubscribeCrosshairMove(handleCrosshairMove);
            chart.remove();
        };
    }, [analysisData, isFullScreen, visibleLayers]); // Re-run when toggle changes

    // Separate Effect: Update Visibility for MA Series (cheaper than repaint)
    useEffect(() => {
        const { ma20Series, ma50Series, ma150Series, ma200Series } = seriesRef.current;
        const showMaLines = visibleLayers.includes('maPriceLines');

        const applyOptions = (series, layerKey) => {
            if (series) {
                const isSeriesVisible = visibleLayers.includes(layerKey);
                series.applyOptions({ 
                    visible: isSeriesVisible,
                    // Only show price line if the series itself is visible AND the MA lines toggle is on
                    priceLineVisible: isSeriesVisible && showMaLines,
                    lastValueVisible: isSeriesVisible && showMaLines
                });
            }
        };

        applyOptions(ma20Series, 'ma20');
        applyOptions(ma50Series, 'ma50');
        applyOptions(ma150Series, 'ma150');
        applyOptions(ma200Series, 'ma200');
    }, [visibleLayers]);


    return (
        <Box position="relative">
            <ChartLegend ticker={analysisData?.ticker} legendData={legendData} />
            <Box ref={chartContainerRef} w="100%" h={isFullScreen ? "calc(100vh - 100px)" : "500px"} />
            {analysisData?.analysis && (
                <Text mt={2} fontStyle="italic" color="gray.400" fontSize="sm">
                    {analysisData.analysis.message}
                </Text>
            )}
        </Box>
    );
};

const ChartPanel = ({ analysisData, loading }) => {
    const [isFullScreen, setIsFullScreen] = useState(false);
    // State for managing visible layers
    const [visibleLayers, setVisibleLayers] = useState([
        'priceLines', 'maPriceLines', // Features defaults
        'ma20', 'ma50', 'ma150', 'ma200' // Series defaults
    ]);

    const toggleFullScreen = () => setIsFullScreen(!isFullScreen);

    const containerStyles = isFullScreen ? {
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        zIndex: 9999, borderRadius: 0, h: '100vh', w: '100vw', m: 0
    } : {
        position: 'relative', minH: '100%', h: '100%' 
    };

    const vcpStatus = analysisData?.vcp_pass ?? analysisData?.passed ?? null; 
    // Use rejection_reason if available for the failed state
    const rejectionReason = analysisData?.chart_data?.rejection_reason;
    const footprint = analysisData?.vcpFootprint || analysisData?.vcp_footprint || "N/A";

    return (
        <Box 
            bg="gray.800" 
            p={isFullScreen ? 6 : 6} 
            borderRadius="lg" 
            boxShadow="xl" 
            transition="all 0.3s ease"
            {...containerStyles}
        >
            <Flex justify="space-between" align="center" mb={4}>
                <HStack spacing={4}>
                    <Heading as="h2" size="lg" color="blue.400" display="flex" alignItems="center" gap={2}>
                        <Activity size={24} /> VCP Analysis
                    </Heading>
                    
                    {!loading && analysisData && (
                        <HStack display={{ base: 'none', md: 'flex' }}>
                             {/* Badge Status */}
                             {vcpStatus !== null && (
                                <Badge 
                                    colorScheme={vcpStatus ? 'green' : 'red'} 
                                    variant="subtle" 
                                    fontSize="0.9em" 
                                    px={2} py={1} 
                                    borderRadius="md"
                                >
                                    {/* Show "FAILED: Reason" if rejected, otherwise "PASSES" */}
                                    {vcpStatus ? "PASSES" : (rejectionReason ? `FAILED: ${rejectionReason}` : "FAILED")}
                                </Badge>
                             )}
                            
                            {/* Footprint Badge - HIDDEN if VCP failed */}
                            {vcpStatus && (
                                <Badge 
                                    colorScheme="purple" 
                                    variant="subtle" 
                                    fontSize="0.9em" 
                                    px={2} py={1} 
                                    borderRadius="md" 
                                    display="flex" 
                                    alignItems="center" 
                                    gap={1}
                                >
                                    <Footprints size={14} /> 
                                    {footprint}
                                </Badge>
                            )}
                        </HStack>
                    )}
                </HStack>

                <HStack>
                     {/* Centralized Layers Menu */}
                     <Menu closeOnSelect={false}>
                        <Tooltip label="Chart Layers" hasArrow>
                            <MenuButton 
                                as={IconButton} 
                                icon={<Layers size={20} />} 
                                variant="ghost" 
                                color="gray.400"
                                _hover={{ color: "white", bg: "gray.700" }}
                                aria-label="Toggle Layers"
                            />
                        </Tooltip>
                        <MenuList bg="gray.800" borderColor="gray.600" color="gray.200">
                            <MenuOptionGroup 
                                title="Chart Elements" 
                                type="checkbox" 
                                value={visibleLayers} 
                                onChange={(values) => setVisibleLayers(values)}
                            >
                                <MenuItemOption value="priceLines">Pivot & Stops (Price Lines)</MenuItemOption>
                                <MenuItemOption value="maPriceLines">MA Last Values (Dotted)</MenuItemOption>
                            </MenuOptionGroup>
                            <MenuDivider />
                            <MenuOptionGroup 
                                title="Moving Averages" 
                                type="checkbox" 
                                value={visibleLayers} 
                                onChange={(values) => setVisibleLayers(values)}
                            >
                                <MenuItemOption value="ma20">MA 20 (Pink)</MenuItemOption>
                                <MenuItemOption value="ma50">MA 50 (Red)</MenuItemOption>
                                <MenuItemOption value="ma150">MA 150 (Orange)</MenuItemOption>
                                <MenuItemOption value="ma200">MA 200 (Green)</MenuItemOption>
                            </MenuOptionGroup>
                        </MenuList>
                    </Menu>

                    {/* Full Screen Button */}
                    <Tooltip label={isFullScreen ? "Exit Fullscreen" : "Fullscreen"} hasArrow>
                        <IconButton 
                            icon={isFullScreen ? <Minimize2 size={20} /> : <Maximize2 size={20} />}
                            onClick={toggleFullScreen}
                            aria-label="Toggle Fullscreen"
                            variant="ghost"
                            color="gray.400"
                            _hover={{ color: "white", bg: "gray.700" }}
                        />
                    </Tooltip>
                </HStack>
            </Flex>

            {loading ? (
                <Flex justify="center" align="center" h="500px">
                    <Spinner color="blue.300" size="xl" />
                </Flex>
            ) : (
                <AnalysisChart analysisData={analysisData} isFullScreen={isFullScreen} visibleLayers={visibleLayers} />
            )}
        </Box>
    );
};

export default ChartPanel;