// frontend-app/src/components/ScreeningPanel.jsx

import React from 'react';
import { 
    Box, Heading, Text, VStack, HStack, Tag, Spinner, 
    Icon, Divider, Badge, Card, CardBody, Flex 
} from '@chakra-ui/react';
import { CheckCircle, XCircle, AlertCircle } from 'lucide-react';

const StatusRow = ({ label, passed }) => (
    <HStack justify="space-between" w="100%" py={1}>
        <Text fontSize="sm" color="gray.400" textTransform="capitalize">
            {label.replace(/_/g, ' ')}
        </Text>
        <Icon 
            as={passed ? CheckCircle : XCircle} 
            color={passed ? 'green.400' : 'red.400'} 
            boxSize={4} 
        />
    </HStack>
);

const ScreeningResult = ({ result, loading }) => {
    if (loading) return <Spinner color="blue.300" alignSelf="center" />;
    
    if (!result) return (
        <VStack spacing={4} align="center" py={10}>
            <Icon as={AlertCircle} boxSize={10} color="gray.600" />
            <Text color="gray.500" fontSize="sm" textAlign="center">
                Enter a ticker to see screening results.
            </Text>
        </VStack>
    );

    return (
        <VStack spacing={4} align="stretch">
            {/* Overall Status Card */}
            <Box 
                bg={result.passes ? 'rgba(72, 187, 120, 0.1)' : 'rgba(245, 101, 101, 0.1)'} 
                p={4} 
                borderRadius="md" 
                borderLeft="4px solid" 
                borderColor={result.passes ? 'green.400' : 'red.400'}
            >
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase">
                    SEPA Template
                </Text>
                <HStack justify="space-between" mt={1}>
                    <Text fontSize="2xl" fontWeight="black" color={result.passes ? 'green.400' : 'red.400'}>
                        {result.passes ? 'PASSED' : 'FAILED'}
                    </Text>
                    <Badge colorScheme={result.passes ? 'green' : 'red'} variant="solid" fontSize="0.8em">
                        {result.ticker}
                    </Badge>
                </HStack>
                {result.reason && (
                    <Text fontSize="xs" color={result.passes ? 'green.200' : 'red.200'} mt={2} noOfLines={3}>
                        {result.reason}
                    </Text>
                )}
            </Box>

            <Divider borderColor="gray.600" />

            {/* Criteria List */}
            <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.500" mb={3} textTransform="uppercase">
                    Screening Criteria
                </Text>
                <VStack spacing={2} align="stretch">
                    {result.details && Object.entries(result.details).map(([key, value]) => (
                        <StatusRow key={key} label={key} passed={value} />
                    ))}
                </VStack>
            </Box>
        </VStack>
    );
};

const ScreeningPanel = ({ result, loading }) => {
    return (
        <Card bg="gray.800" shadow="xl" borderRadius="lg" h="100%" variant="outline" borderColor="gray.700">
            <CardBody p={6}>
                 {/* Aligned Header: Matches ChartPanel's Heading size and gap */}
                 <Flex justify="space-between" align="center" mb={4}>
                    <Heading as="h2" size="lg" color="blue.400" display="flex" alignItems="center" gap={2}>
                        <Icon as={CheckCircle} boxSize={6} /> {/* 24px matches 'Activity' icon */}
                        Screening Result
                    </Heading>
                </Flex>
                
                <ScreeningResult result={result} loading={loading} />
            </CardBody>
        </Card>
    );
};

export default ScreeningPanel;