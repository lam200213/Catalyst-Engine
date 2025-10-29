// frontend-app/src/components/LeadingIndustriesTable.jsx

import React from 'react';
import {
    Box, Heading, Table, Thead, Tbody, Tr, Th, Td, TableContainer,
    VStack, HStack, Text, Tag
} from '@chakra-ui/react';

const LeadingIndustriesTable = ({ marketLeaders }) => {
  // Normalize to an array of { industry, stocks }
  const normalizeLeaders = (leaders) => {
    if (!leaders) return [];
    const li = leaders.leading_industries;
    // Case 1: correct shape (Array)
    if (Array.isArray(li)) return li;
    // Case 2: backend returns keyed object like { "Semiconductors": ["NVDA", ...], ... }
    if (li && typeof li === 'object') {
      return Object.entries(li).map(([industry, stocks]) => {
        const normalizedStocks = Array.isArray(stocks)
          ? (typeof stocks[0] === 'string'
              ? stocks.map((t) => ({ ticker: t, percent_change_3m: null }))
              : stocks)
          : [];
        return { industry, stocks: normalizedStocks };
      });
    }
    // Fallback
    return [];
  };

  const industries = normalizeLeaders(marketLeaders);

  if (!industries.length) {
    return (
      <Box>
        <Heading size="md" mb={3}>Leading Industries & Stocks</Heading>
        <Text color="gray.400">No leaders available.</Text>
      </Box>
    );
  }

  return (
    <Box>
      <Heading size="md" mb={3}>Leading Industries & Stocks</Heading>
      <TableContainer>
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              <Th>Industry</Th>
              <Th>Leading Stocks (3-Month Return)</Th>
            </Tr>
          </Thead>
          <Tbody>
            {industries.map(({ industry, stocks }) => (
              <Tr key={industry}>
                <Td>{industry}</Td>
                <Td>
                  <VStack align="start" spacing={1}>
                    {(stocks || []).map(({ ticker, percent_change_3m }) => (
                      <HStack key={ticker} spacing={2}>
                        <Tag>{ticker}</Tag>
                        <Text>
                          {percent_change_3m !== null && percent_change_3m !== undefined
                            ? `${percent_change_3m.toFixed(1)}%`
                            : '—'}
                        </Text>
                      </HStack>
                    ))}
                  </VStack>
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