// frontend-app/src/pages/MarketPage.jsx

import React from 'react';
import { Box, Heading, VStack, SimpleGrid } from '@chakra-ui/react';
import MarketHealthCard from '../components/MarketHealthCard';
import LeadingIndustriesTable from '../components/LeadingIndustriesTable';
import { mockMarketHealthResponse } from '../services/mockData';

const MarketPage = () => {
    // TODO (Day 4): Replace mock data with live API call using useMonitoringApi hook.
    // const { data, loading, error } = useMonitoringApi(getMarketHealth);
    const data = mockMarketHealthResponse;
    const loading = false;
    const error = null;

    return (
        <Box>
        <Heading as="h1" size="lg" color="blue.300" mb={6}>Market Health</Heading>

            {/* Placeholder for loading state */}
            {/* TODO (Day 4): Wire up loading state from API hook. */}
            {loading && (
                <Text color="blue.400" mb={4}>Loading market health…</Text>
            )}

            {/* Placeholder for error state */}
            {/* TODO (Day 4): Wire up error state from API hook. */}
            {error && (
                <Text color="red.500" mb={4}>{String(error)}</Text>
            )}

            {/* Main content render block (Gone: previously empty) */}
            {data && !loading && !error && (
                <SimpleGrid columns={{ base: 1, md: 2 }} spacing={6}>
                {/* Pass mock market_overview to MarketHealthCard */}
                <MarketHealthCard marketOverview={data.market_overview} />
                {/* Pass mock leaders_by_industry to LeadingIndustriesTable */}
                <LeadingIndustriesTable marketLeaders={data.leaders_by_industry} />
                </SimpleGrid>
            )}
        </Box>
    );
};

export default MarketPage;