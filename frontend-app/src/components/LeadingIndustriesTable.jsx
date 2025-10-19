// frontend-app/src/components/LeadingIndustriesTable.jsx

import React from 'react';
import {
    Box, Heading, Table, Thead, Tbody, Tr, Th, Td, TableContainer,
    VStack, HStack, Text, Tag
} from '@chakra-ui/react';

const LeadingIndustriesTable = ({ marketLeaders }) => {
    return (
        <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="xl">
            <Heading as="h3" size="md" color="blue.300" mb={4}>
                Leading Industries & Stocks
            </Heading>
            <TableContainer>
                <Table variant="simple" size="sm">
                    <Thead>
                        <Tr>
                            <Th>Industry</Th>
                            <Th>Leading Stocks (1-Month Return)</Th>
                        </Tr>
                    </Thead>
                    <Tbody>
                        {marketLeaders.leading_industries.map(({ industry, stocks }) => (
                            <Tr key={industry}>
                                <Td>
                                    <Text fontWeight="medium">{industry}</Text>
                                </Td>
                                <Td>
                                    <HStack spacing={2}>
                                        {stocks.map(({ ticker, percent_change_1m }) => (
                                            <Tag key={ticker} colorScheme="green" variant="subtle">
                                                {ticker}: {percent_change_1m.toFixed(1)}%
                                            </Tag>
                                        ))}
                                    </HStack>
                                </Td>
                            </Tr>
                        ))}
                    </Tbody>
                </Table>
            </TableContainer>
        </Box>
    );
};

export default LeadingIndustriesTable;