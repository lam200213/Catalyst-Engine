// frontend-app/src/components/ScreeningResult.jsx
import React from 'react';
import { Box, Heading, Text, SimpleGrid, Flex, Tag, Spinner } from '@chakra-ui/react';

const ScreeningResult = ({ result, loading }) => {
    if (loading) return <Spinner color="blue.300" />;
    if (!result) return <Text color="gray.400">Results will appear here.</Text>;

    const renderDetails = () => (
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4} mt={4}>
            {Object.entries(result.details).map(([key, value]) => (
                <Flex key={key} justify="space-between" align="center">
                    <Text fontSize="sm" color="gray.400" textTransform="capitalize">
                        {key.replace(/_/g, ' ')}
                    </Text>
                    <Tag colorScheme={value ? 'green' : 'red'} size="sm">
                        {value ? 'Pass' : 'Fail'}
                    </Tag>
                </Flex>
            ))}
        </SimpleGrid>
    );

    return (
        <Box>
            <Text fontSize="md" color="gray.400">Overall Result for {result.ticker}</Text>
            <Text fontSize="3xl" fontWeight="bold" color={result.passes ? 'green.300' : 'red.300'}>
                {result.passes ? 'PASS' : 'FAIL'}
            </Text>
            {result.reason && <Text fontSize="sm" color="gray.500" mt={1}>{result.reason}</Text>}
            {result.details && renderDetails()}
        </Box>
    );
};

export default ScreeningResult;