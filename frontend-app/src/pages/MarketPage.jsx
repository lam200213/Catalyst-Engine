// frontend-app/src/pages/MarketPage.jsx

import React from 'react';
import { Box, Heading, VStack, SimpleGrid } from '@chakra-ui/react';
import MarketHealthCard from '../components/MarketHealthCard';
import LeadingIndustriesTable from '../components/LeadingIndustriesTable';
import { mockMarketHealthResponse } from '../services/mockData';
import { useMonitoringApi } from '../hooks/useMonitoringApi';
import { getMarketHealth } from '../services/monitoringApi';

const MarketPage = () => {
    const { data, loading, error } = useMonitoringApi(getMarketHealth);

return (
        <Box p={6}>
            <Heading size="lg" mb={4}>Market Health</Heading>

            {loading && (
                <Center h="200px">
                    <VStack>
                        <Spinner size="xl" color="blue.400" />
                        <Text color="blue.400" mt={4}>Loading market health…</Text>
                    </VStack>
                </Center>
            )}

            {error && (
                <Alert status="error" borderRadius="md">
                    <AlertIcon />
                    {String(error)}
                </Alert>
            )}

            {/* Check for data before rendering children */}
            {data && !loading && !error && (
                <SimpleGrid columns={{ base: 1, md: 2 }} spacing={6}>
                    <MarketHealthCard marketOverview={data.market_overview} />
                    <LeadingIndustriesTable marketLeaders={data.leaders_by_industry} />
                </SimpleGrid>
            )}
        </Box>
    );
};

export default MarketPage;