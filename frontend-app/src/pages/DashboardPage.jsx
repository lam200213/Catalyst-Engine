// frontend-app/src/pages/DashboardPage.jsx

import React from 'react';
import {
  Box, Grid, GridItem, Heading, Text, VStack,
  Alert, AlertIcon, Flex, useColorModeValue
} from '@chakra-ui/react';
import { useStockData } from '../hooks/useStockData';
import ScreeningPanel from '../components/ScreeningPanel';
import ChartPanel from '../components/ChartPanel';
import TickerForm from '../components/TickerForm';

function DashboardPage() {
  // Reuse existing hooks and state
  const { ticker, setTicker, data, loading, error, getData } = useStockData('AAPL');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (ticker) {
      getData(ticker);
    }
  };

  const bgColor = useColorModeValue('gray.50', 'gray.900');

  return (
    <Box minH="100vh" p={4} bg={bgColor}>
      <VStack spacing={4} align="stretch">
        {/* Header Section */}
        <Flex 
          justify="space-between" 
          align="center" 
          bg="gray.800" 
          p={4} 
          borderRadius="lg" 
          boxShadow="md"
          direction={{ base: 'column', md: 'row' }}
          gap={4}
        >
          <Box>
            <Heading as="h1" size="lg" color="blue.400">
              SEPA Stock Screener
            </Heading>
            <Text color="gray.400" fontSize="sm">
              Mark Minervini's Volatility Contraction Pattern Analysis
            </Text>
          </Box>
          
          <Box w={{ base: '100%', md: 'auto' }}>
            <TickerForm 
              ticker={ticker}
              setTicker={setTicker}
              handleSubmit={handleSubmit}
              loading={loading}
            />
          </Box>
        </Flex>

        {error && (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {error}
          </Alert>
        )}

        {/* Main Content Grid: Screening (Left/Sidebar) vs Chart (Right/Main) */}
        <Grid
          templateColumns={{ base: "1fr", lg: "320px 1fr" }}
          gap={6}
          alignItems="stretch" /* Changed from 'start' to 'stretch' to match heights */
        >
          {/* Left Column: Screening Results (Sidebar Style) */}
          <GridItem w="100%">
            <ScreeningPanel 
              result={data.screening} 
              loading={loading && !data.screening} 
            />
          </GridItem>

          {/* Right Column: VCP Analysis (Main View) */}
          <GridItem w="100%">
            <ChartPanel 
              analysisData={data.analysis} 
              loading={loading && !data.analysis} 
            />
          </GridItem>
        </Grid>

        <Box as="footer" textAlign="center" py={4} color="gray.600" fontSize="xs">
          <Text>&copy; {new Date().getFullYear()} SEPA Stock Screener. All rights reserved.</Text>
        </Box>
      </VStack>
    </Box>
  );
}

export default DashboardPage;