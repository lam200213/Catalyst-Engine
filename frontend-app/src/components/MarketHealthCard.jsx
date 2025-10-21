// frontend-app/src/components/MarketHealthCard.jsx

import React from 'react';
import { Box, Heading, SimpleGrid, Text, Stat, StatLabel, StatNumber, Skeleton }  from '@chakra-ui/react';

const MarketHealthCard = ({ marketOverview, loading = false }) => {
    // Null safety and loading states
    if (loading) {
        return (
        <Box p={6} bg="gray.700" borderRadius="lg" shadow="md">
            <Skeleton height="24px" mb={4} />
            <SimpleGrid columns={{ base: 2, md: 5 }} spacing={4}>
            {[1,2,3,4,5].map(i => (
                <Box key={i}>
                <Skeleton height="16px" mb={2} />
                <Skeleton height="24px" />
                </Box>
            ))}
            </SimpleGrid>
        </Box>
        );
    }

    // Handle missing data gracefully
    if (!marketOverview) {
        return (
        <Box p={6} bg="gray.700" borderRadius="lg" shadow="md">
            <Text color="gray.400">Market data unavailable</Text>
        </Box>
        );
    }

    const {
        market_stage = 'Unknown',
        correction_depth_percent = 0,
        new_highs = 0,
        new_lows = 0,
        high_low_ratio = 0,
    } = marketOverview;

    // Dynamic color based on market stage
    const getStageColor = (stage) => {
        switch (stage) {
        case 'Bullish': return 'green.400';
        case 'Bearish': return 'red.400';
        case 'Recovery': return 'blue.400';
        default: return 'gray.400';
        }
    };


    return (
        <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="xl">
            <Heading as="h3" size="md" color="blue.300" mb={4}>
                Market Overview
            </Heading>
            <SimpleGrid columns={{ base: 2, md: 3 }} spacing={6}>
                <Stat>
                    <StatLabel color="gray.400">Stage</StatLabel>
                    <StatNumber color={getStageColor(market_stage)}>
                        {market_stage}
                    </StatNumber>
                </Stat>
                <Stat>
                    <StatLabel color="gray.400">Correction Depth</StatLabel>
                    <StatNumber>{correction_depth_percent.toFixed(1)}%</StatNumber>
                </Stat>
                <Stat>
                    <StatLabel color="gray.400">Highs:Lows Ratio</StatLabel>
                    <StatNumber>{high_low_ratio.toFixed(1)} : 1</StatNumber>
                </Stat>
                <Stat>
                    <StatLabel color="gray.400">New Highs</StatLabel>
                    <StatNumber>{new_highs}</StatNumber>
                </Stat>
                <Stat>
                    <StatLabel color="gray.400">New Lows</StatLabel>
                    <StatNumber>{new_lows}</StatNumber>
                </Stat>
            </SimpleGrid>
        </Box>
    );
};

export default MarketHealthCard;