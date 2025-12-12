// frontend-app/src/components/MarketIndicesWidget.jsx
import React from 'react';
import { 
    Box, Tabs, TabList, Tab, TabPanels, TabPanel, 
    Skeleton, Text, Flex, useColorModeValue 
} from '@chakra-ui/react';
import ChartPanel from './ChartPanel';

const INDICES = [
    { key: '^GSPC', label: 'S&P 500' },
    { key: '^IXIC', label: 'Nasdaq' },
    { key: '^DJI', label: 'Dow Jones' },
];

const MarketIndicesWidget = ({ indicesData, loading }) => {
    const bg = useColorModeValue('white', 'gray.800');
    const borderColor = useColorModeValue('gray.200', 'gray.700');
    // Latest Add: Move hook to top level to prevent "Rendered fewer hooks than expected" error
    const tabListBg = useColorModeValue('gray.50', 'gray.900');

    if (loading) {
        return (
            <Box p={6} bg={bg} borderRadius="lg" boxShadow="md" borderWidth="1px" borderColor={borderColor}>
                <Skeleton height="40px" mb={4} width="300px" />
                <Skeleton height="400px" />
            </Box>
        );
    }

    if (!indicesData) {
        // Fallback or empty state
        return null; 
    }

    return (
        <Box bg={bg} borderRadius="lg" boxShadow="xl" overflow="hidden" borderWidth="1px" borderColor={borderColor}>
            <Tabs isLazy variant="line" colorScheme="blue" defaultIndex={0}>
                {/* Use the pre-calculated variable here instead of calling the hook inline */}
                <Flex borderBottomWidth="1px" borderColor={borderColor} px={4} bg={tabListBg}>
                    <TabList borderBottom="none">
                        {INDICES.map(({ key, label }) => (
                            <Tab key={key} fontWeight="semibold" py={4} _selected={{ color: 'blue.400', borderColor: 'blue.400', borderBottomWidth: '2px', mb: '-2px' }}>
                                {label}
                            </Tab>
                        ))}
                    </TabList>
                </Flex>

                <TabPanels>
                    {INDICES.map(({ key }) => {
                        const data = indicesData[key];
                        // If data is missing for a specific index, handle gracefully
                        if (!data) return <TabPanel key={key}><Text p={4}>No data available for {key}</Text></TabPanel>;

                        return (
                            <TabPanel key={key} p={0}>
                                {/* Reuse ChartPanel. We pass loading=false because parent handles loading state */}
                                <ChartPanel analysisData={data} loading={false} />
                            </TabPanel>
                        );
                    })}
                </TabPanels>
            </Tabs>
        </Box>
    );
};

export default MarketIndicesWidget;