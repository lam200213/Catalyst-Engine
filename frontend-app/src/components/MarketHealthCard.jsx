// frontend-app/src/components/MarketHealthCard.jsx

import React from 'react';
import { 
    Box, 
    SimpleGrid, 
    Stat, 
    StatLabel, 
    StatNumber, 
    StatHelpText, 
    StatArrow, 
    useColorModeValue,
    Heading,
    Flex,
    Text,
    Icon,
    Tooltip
} from '@chakra-ui/react';
import { InfoIcon } from '@chakra-ui/icons';

const MetricStat = ({ label, value, helpText, arrow, helpIcon }) => {
    const bg = useColorModeValue('white', 'gray.700');
    return (
        <Stat
            px={{ base: 2, md: 4 }}
            py={'4'} // Reduced vertical padding
            shadow={'xl'}
            border={'1px solid'}
            borderColor={useColorModeValue('gray.200', 'gray.600')}
            rounded={'lg'}
            bg={bg}
        >
            <Flex justifyContent={'space-between'}>
                <Box pl={{ base: 2, md: 4 }}>
                    <StatLabel fontWeight={'medium'} isTruncated display="flex" alignItems="center" gap={1}>
                        {label}
                        {helpIcon && (
                            <Tooltip label={helpIcon} fontSize="sm">
                                <InfoIcon w={3} h={3} color="gray.400" />
                            </Tooltip>
                        )}
                    </StatLabel>
                    <StatNumber fontSize={'2xl'} fontWeight={'medium'}>
                        {value}
                    </StatNumber>
                    {helpText && (
                        <StatHelpText mb="0"> {/* Remove bottom margin to tighten layout */}
                            {arrow && <StatArrow type={arrow} />}
                            {helpText}
                        </StatHelpText>
                    )}
                </Box>
            </Flex>
        </Stat>
    );
};

const MarketHealthCard = ({ marketOverview }) => {
    if (!marketOverview) return null;

    const { 
        market_stage, 
        correction_depth_percent, 
        new_highs, 
        new_lows, 
        high_low_ratio,
        as_of_date 
    } = marketOverview;

    const isBullish = market_stage === 'Bullish';
    const isBearish = market_stage === 'Bearish';
    
    // Formatting date
    const formattedDate = as_of_date 
        ? new Date(as_of_date).toLocaleDateString(undefined, { 
            year: 'numeric', 
            month: 'short', 
            day: 'numeric' 
          }) 
        : null;

    return (
        <Box p={4}> {/* Reduced container padding from 6 to 4 */}
            {/* Header with Date - Aligned with Dashboard Style */}
            <Flex justify="space-between" align="center" mb={4}> {/* Reduced margin bottom */}
                <Box>
                    <Heading as="h1" size="lg" color="blue.400">
                        Market Health Overview
                    </Heading>
                    <Text color="gray.500" fontSize="sm" mt={1}>
                        Key indicators and breadth analysis
                    </Text>
                </Box>
                {formattedDate && (
                    <Text fontSize="xs" color="gray.400" fontStyle="italic" bg="gray.700" px={2} py={1} borderRadius="md">
                        As of: {formattedDate}
                    </Text>
                )}
            </Flex>

            <SimpleGrid columns={{ base: 1, md: 2, lg: 4 }} spacing={{ base: 4, lg: 6 }}> {/* Tighter grid spacing */}
                <MetricStat 
                    label="Market Stage" 
                    value={market_stage} 
                    helpText={isBullish ? "Uptrend" : isBearish ? "Downtrend" : "Choppy"}
                    arrow={isBullish ? 'increase' : isBearish ? 'decrease' : undefined}
                />
                
                <MetricStat 
                    label="Correction Depth" 
                    value={`${correction_depth_percent}%`} 
                    helpText="From 52-Week High"
                    helpIcon="Percentage decline of the S&P 500 from its 52-week high."
                />

                <MetricStat 
                    label="High/Low Ratio" 
                    value={high_low_ratio?.toFixed(2)} 
                    helpText={`${new_highs} Highs / ${new_lows} Lows`}
                    arrow={high_low_ratio > 1 ? 'increase' : 'decrease'}
                    helpIcon="Ratio of stocks making new 52-week highs vs lows. >1 is bullish."
                />

                <MetricStat 
                    label="Net New Highs" 
                    value={new_highs - new_lows}
                    helpText="Breadth Indicator"
                    arrow={(new_highs - new_lows) > 0 ? 'increase' : 'decrease'}
                />
            </SimpleGrid>
        </Box>
    );
};

export default MarketHealthCard;