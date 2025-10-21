// frontend-app/src/pages/MarketPage.jsx

import React from 'react';
import { Box, Heading, VStack, SimpleGrid, Button, Alert, AlertIcon } from '@chakra-ui/react';
import MarketHealthCard from '../components/MarketHealthCard';
import LeadingIndustriesTable from '../components/LeadingIndustriesTable';
import { useMonitoringApi } from '../hooks/useMonitoringApi';
import { getMarketHealth } from '../services/monitoringApi';

const MarketPage = () => {
  const { data, loading, error, retry } = useMonitoringApi(getMarketHealth);

  // Enhanced error handling with retry option
  if (error) {
    return (
      <Box p={6}>
        <VStack spacing={6}>
          <Heading size="xl" color="whiteAlpha.900">Market Health</Heading>
          <Alert status="error" borderRadius="lg">
            <AlertIcon />
            <Box flex="1">
              <Text>{error}</Text>
              <Button 
                mt={2} 
                size="sm" 
                colorScheme="red" 
                variant="outline"
                onClick={retry}
              >
                Try Again
              </Button>
            </Box>
          </Alert>
        </VStack>
      </Box>
    );
  }

  return (
    <Box p={6}>
    <VStack spacing={6} align="stretch">
        <Heading size="xl" color="whiteAlpha.900">
        Market Health
        </Heading>
        
        <SimpleGrid columns={{ base: 1, lg: 1 }} spacing={6}>
        <MarketHealthCard 
            marketOverview={data?.market_overview} 
            loading={loading} 
        />
        
        {data?.leaders_by_industry && (
            <LeadingIndustriesTable 
            marketLeaders={data.leaders_by_industry}
            loading={loading}
            />
        )}
        </SimpleGrid>
    </VStack>
    </Box>
  );
};

export default MarketPage;