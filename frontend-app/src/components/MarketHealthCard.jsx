// frontend-app/src/components/MarketHealthCard.jsx

import React from 'react';
import { Box, Heading, SimpleGrid, Text, Stat, StatLabel, StatNumber } from '@chakra-ui/react';

const MarketHealthCard = ({ marketOverview }) => {
    const {
        market_stage,
        market_correction_depth,
        new_highs,
        new_lows,
        high_low_ratio,
    } = marketOverview;

    const stageColor = market_stage === 'Bullish' ? 'green.400' : 'red.400';

    return (
        <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="xl">
            <Heading as="h3" size="md" color="blue.300" mb={4}>
                Market Overview
            </Heading>
            <SimpleGrid columns={{ base: 2, md: 3 }} spacing={6}>
                <Stat>
                    <StatLabel color="gray.400">Stage</StatLabel>
                    <StatNumber color={stageColor}>{market_stage}</StatNumber>
                </Stat>
                <Stat>
                    <StatLabel color="gray.400">Correction Depth</StatLabel>
                    <StatNumber>{market_correction_depth.toFixed(1)}%</StatNumber>
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