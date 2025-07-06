// frontend-app/src/components/ChartLegend.jsx
import React from 'react';
import { Box, Text, VStack, HStack, Flex, Circle } from '@chakra-ui/react';

const formatValue = (value) => {
    return typeof value === 'number' ? value.toFixed(2) : 'N/A';
};

const formatVolume = (value) => {
    if (typeof value !== 'number') return 'N/A';
    if (value > 1_000_000) {
        return `${(value / 1_000_000).toFixed(2)}M`;
    }
    if (value > 1_000) {
        return `${(value / 1_000).toFixed(1)}K`;
    }
    return value.toString();
};

const ChartLegend = ({ ticker, legendData }) => {
    if (!legendData || !legendData.ohlcv) {
        return null; // Don't render anything if there's no data
    }

    const { ohlcv, mas } = legendData;

    return (
        <Box
            position="absolute"
            top="15px"
            left="15px"
            zIndex="10"
            bg="rgba(26, 32, 44, 0.85)"
            p={3}
            borderRadius="md"
            boxShadow="lg"
            pointerEvents="none" // Make sure the legend doesn't block chart interactions
            color="gray.200"
            minW="200px"
        >
            <VStack align="stretch" spacing={1}>
                <Text fontWeight="bold" fontSize="lg" color="blue.300">{ticker}</Text>
                <Text fontSize="sm" color="gray.400">{ohlcv.time}</Text>

                <HStack justify="space-between" spacing={4} fontSize="sm">
                    <Text>O: <Text as="span" color="white">{formatValue(ohlcv.open)}</Text></Text>
                    <Text>H: <Text as="span" color="white">{formatValue(ohlcv.high)}</Text></Text>
                    <Text>L: <Text as="span" color="white">{formatValue(ohlcv.low)}</Text></Text>
                    <Text>C: <Text as="span" color="white">{formatValue(ohlcv.close)}</Text></Text>
                </HStack>

                {/* Display the formatted volume */}
                <Flex justify="space-between" fontSize="xs" mt={2}>
                    <Text>Volume:</Text>
                    <Text>{formatVolume(ohlcv.volume)}</Text>
                </Flex>

                <VStack align="stretch" spacing={0} mt={1}>
                    {mas.map(ma => (
                        ma.value ? (
                            <Flex key={ma.name} justify="space-between" fontSize="xs">
                                <HStack>
                                    <Circle size="8px" bg={ma.color} />
                                    <Text>{ma.name}:</Text>
                                </HStack>
                                <Text>{formatValue(ma.value)}</Text>
                            </Flex>
                        ) : null
                    ))}
                </VStack>
            </VStack>
        </Box>
    );
};

export default ChartLegend;