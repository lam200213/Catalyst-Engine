// frontend-app/src/pages/MarketPage.jsx
import React from 'react';
import { Box, Heading, VStack, SimpleGrid, Button, Alert, AlertIcon, Spinner } from '@chakra-ui/react';
import MarketHealthCard from '../components/MarketHealthCard';
import LeadingIndustriesTable from '../components/LeadingIndustriesTable';
import { useMarketHealthQuery } from '../hooks/useMarketHealthQuery';

const MarketPage = () => {
  const { data, isLoading, error, refetch, isFetching } = useMarketHealthQuery();

  // Enhanced error handling with retry option
  if (error) {
    return (
      <Box p={6}>
        <Heading size="lg" mb={4}>Market Health</Heading>
        <Alert status="error" mb={4}>
          <AlertIcon />
          {error.message || 'Failed to load market health.'}
        </Alert>
        <Button onClick={() => refetch()} colorScheme="blue">Try Again</Button>
      </Box>
    );
  }

  const marketOverview = data?.market_overview ?? null;
  const marketLeaders = data?.leaders_by_industry ?? { leading_industries: [] };

  return (
    <VStack align="stretch" spacing={6} p={6}>
      <Heading size="lg">Market Health</Heading>

      <MarketHealthCard marketOverview={marketOverview} loading={isLoading || isFetching} />

      {!isLoading && (
        <LeadingIndustriesTable marketLeaders={marketLeaders} />
      )}
    </VStack>
  );
};

export default MarketPage;