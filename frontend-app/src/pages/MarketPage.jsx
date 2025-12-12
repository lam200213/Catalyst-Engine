// frontend-app/src/pages/MarketPage.jsx
import React from 'react';
import { 
    Box, Grid, GridItem, Skeleton, Alert, AlertIcon, 
    Container, VStack, useColorModeValue 
} from '@chakra-ui/react';
import { useMarketHealthQuery } from '../hooks/useMarketHealthQuery';
import MarketHealthCard from '../components/MarketHealthCard';
import LeadingIndustriesTable from '../components/LeadingIndustriesTable';
import MarketIndicesWidget from '../components/MarketIndicesWidget';
import ErrorBoundary from '../components/ErrorBoundary';

const MarketPage = () => {
    // 1. Fetch Data
    const { data, isLoading, isError, error } = useMarketHealthQuery();
    
    // 2. Destructure payload with fallbacks
    const marketOverview = data?.market_overview;
    const marketLeaders = data?.leaders_by_industry;
    const indicesAnalysis = data?.indices_analysis; // New field

    // 3. Dynamic Background
    const bg = useColorModeValue('gray.50', 'gray.900');

    // 4. Loading State
    if (isLoading) {
        return (
            <Container maxW="container.xl" py={6}>
                <VStack spacing={6} align="stretch">
                    <Skeleton height="150px" borderRadius="lg" />
                    <Skeleton height="500px" borderRadius="lg" />
                    <Skeleton height="300px" borderRadius="lg" />
                </VStack>
            </Container>
        );
    }

    // 5. Error State
    if (isError) {
        return (
            <Container maxW="container.xl" py={6}>
                <Alert status="error" borderRadius="md">
                    <AlertIcon />
                    Unable to load market data: {error?.message || 'Unknown error'}
                </Alert>
            </Container>
        );
    }

    return (
        <Box minH="100vh" bg={bg}>
            <Container maxW="container.xl" py={6} px={{ base: 4, md: 6 }}>
                <VStack spacing={8} align="stretch">
                    
                    {/* Top Row: Market Health Stats */}
                    <ErrorBoundary>
                        <MarketHealthCard marketOverview={marketOverview} />
                    </ErrorBoundary>

                    {/* Middle Row: Major Indices Charts (The "Optimal" Addition) */}
                    <ErrorBoundary>
                        <MarketIndicesWidget 
                            indicesData={indicesAnalysis} 
                            loading={isLoading} 
                        />
                    </ErrorBoundary>

                    {/* Bottom Row: Leading Sectors */}
                    <ErrorBoundary>
                        <LeadingIndustriesTable marketLeaders={marketLeaders} />
                    </ErrorBoundary>

                </VStack>
            </Container>
        </Box>
    );
};

export default MarketPage;