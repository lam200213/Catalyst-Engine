// frontend-app/src/pages/MarketPage.jsx
import React from 'react';
import { 
    Box, Grid, GridItem, Skeleton, Alert, AlertIcon, 
    Container, useColorModeValue, Heading, Text
} from '@chakra-ui/react';
import { useMarketHealthQuery } from '../hooks/useMarketHealthQuery';
import MarketHealthCard from '../components/MarketHealthCard';
import LeadingIndustriesTable from '../components/LeadingIndustriesTable';
import MarketIndicesWidget from '../components/MarketIndicesWidget';
import ErrorBoundary from '../components/ErrorBoundary';

const MarketPage = () => {
    const { data, isLoading, isError, error } = useMarketHealthQuery();
    
    const marketOverview = data?.market_overview;
    const marketLeaders = data?.leaders_by_industry;
    const indicesAnalysis = data?.indices_analysis;

    const pageBg = useColorModeValue('gray.50', 'gray.900');

    if (isLoading) {
        return (
            <Container maxW="container.2xl" py={4} px={4}>
                <Grid templateColumns={{ base: "1fr", lg: "3fr 1fr" }} gap={4}>
                    <GridItem colSpan={{ base: 1, lg: 2 }}>
                        <Skeleton height="150px" borderRadius="xl" />
                    </GridItem>
                    <GridItem colSpan={{ base: 1, lg: 2 }}>
                        <Skeleton height="500px" borderRadius="xl" />
                    </GridItem>
                </Grid>
            </Container>
        );
    }

    if (isError) {
        return (
            <Container maxW="container.2xl" py={4} px={4}>
                <Alert status="error" borderRadius="xl">
                    <AlertIcon />
                    Unable to load market data: {error?.message}
                </Alert>
            </Container>
        );
    }

    return (
        <Box minH="100vh" bg={pageBg}>
            {/* Reduced py to 4 to match Dashboard spacing */}
            <Container maxW="container.2xl" py={4} px={{ base: 4, md: 6 }}>
                
                <Grid 
                    templateColumns={{ base: "1fr", xl: "3fr 1fr" }} 
                    gap={4} // Tight gap
                    alignItems="stretch"
                >
                    
                    {/* Row 1: Market Health Hero */}
                    <GridItem colSpan={{ base: 1, xl: 2 }}>
                        <ErrorBoundary>
                            <Box 
                                bg={useColorModeValue('white', 'gray.800')} 
                                borderRadius="xl" 
                                boxShadow="sm"
                                overflow="hidden"
                            >
                                <MarketHealthCard marketOverview={marketOverview} />
                            </Box>
                        </ErrorBoundary>
                    </GridItem>

                    {/* Row 2, Column 1: Indices Charts */}
                    {/* Reduced height slightly to accommodate the top card without scrolling on 1080p */}
                    <GridItem colSpan={1} minH="480px">
                        <ErrorBoundary>
                            <Box h="100%">
                                <MarketIndicesWidget 
                                    indicesData={indicesAnalysis} 
                                    loading={isLoading} 
                                />
                            </Box>
                        </ErrorBoundary>
                    </GridItem>

                    {/* Row 2, Column 2: Leading Sectors */}
                    <GridItem colSpan={1}>
                        <ErrorBoundary>
                            <Box 
                                bg={useColorModeValue('white', 'gray.800')} 
                                borderRadius="xl" 
                                boxShadow="xl"
                                borderWidth="1px"
                                borderColor={useColorModeValue('gray.200', 'gray.700')}
                                overflow="hidden"
                                h="100%" 
                            >
                                <LeadingIndustriesTable marketLeaders={marketLeaders} />
                            </Box>
                        </ErrorBoundary>
                    </GridItem>

                </Grid>
            </Container>
        </Box>
    );
};

export default MarketPage;