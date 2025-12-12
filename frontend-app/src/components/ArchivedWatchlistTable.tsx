// frontend-app/src/components/ArchivedWatchlistTable.tsx
import React, { useMemo, useState } from 'react';
import {
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  TableContainer,
  Tag,
  IconButton,
  Text,
  Box,
  useColorModeValue,
  Tooltip,
  HStack,
  Flex,
  Icon,
} from '@chakra-ui/react';
import { 
  Trash2, 
  AlertCircle, 
  UserX, 
  Undo2,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  Info 
} from 'lucide-react';
import type { ArchivedWatchlistItem } from '../types/monitoring';

export interface ArchivedWatchlistTableProps {
  items?: ArchivedWatchlistItem[];
  onDelete?: (ticker: string) => void;
  onRestore?: (ticker: string) => void;
  rowActionsDisabled?: boolean;
}

// --- Sorting Types ---
type SortKey = 'ticker' | 'archived_at' | 'reason' | 'failed_stage';
type SortDirection = 'asc' | 'desc';

interface SortConfig {
  key: SortKey;
  direction: SortDirection;
}

const mapReasonToLabel = (reason: string | undefined): { label: string; color: string; icon: any } => {
  // Handle both backend enum formats (snake_case vs direct string) just in case
  switch (reason) {
    case 'MANUAL_DELETE':
    case 'MANUALDELETE':
      return { label: 'Manual delete', color: 'gray', icon: UserX };
    case 'FAILED_HEALTH_CHECK':
    case 'FAILEDHEALTHCHECK':
      return { label: 'Failed health check', color: 'red', icon: AlertCircle };
    default:
      return { label: reason ?? 'Unknown', color: 'gray', icon: AlertCircle };
  }
};

export const ArchivedWatchlistTable: React.FC<ArchivedWatchlistTableProps> = ({
  items,
  onDelete,
  onRestore,
  rowActionsDisabled = false,
}) => {
  const safeItems = Array.isArray(items) ? items : [];
  
  // Theme hooks
  const tableBg = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');
  const activeHeaderBg = useColorModeValue('gray.100', 'gray.700');
  
  // Font Colors - Improved contrast (Brighter in dark mode)
  const dateColor = useColorModeValue('gray.700', 'gray.300');
  const failedStageColor = useColorModeValue('gray.800', 'gray.200');

  // Sorting State - Default to 'archived_at' DESC (Show newest archives first)
  const [sortConfig, setSortConfig] = useState<SortConfig>({
    key: 'archived_at',
    direction: 'desc'
  });

  // Sorting Handler
  const handleSort = (key: SortKey) => {
    let direction: SortDirection = 'asc';
    
    // Default to 'desc' for Dates logic
    if (key === 'archived_at') {
         direction = 'desc'; 
    }

    // Toggle logic if clicking the active column
    if (sortConfig.key === key) {
        direction = sortConfig.direction === 'asc' ? 'desc' : 'asc';
    }
    
    setSortConfig({ key, direction });
  };

  // Memoized Sorted Items
  const sortedItems = useMemo(() => {
    const data = [...safeItems];

    return data.sort((a, b) => {
      let valA: any;
      let valB: any;

      switch (sortConfig.key) {
        case 'ticker':
          valA = a.ticker;
          valB = b.ticker;
          break;
        case 'archived_at':
          // Date comparison
          valA = a.archived_at ? new Date(a.archived_at).getTime() : 0;
          valB = b.archived_at ? new Date(b.archived_at).getTime() : 0;
          break;
        case 'reason':
          // Sort by the visible label, not the internal enum key
          valA = mapReasonToLabel(a.reason).label;
          valB = mapReasonToLabel(b.reason).label;
          break;
        case 'failed_stage':
          // Null strings to bottom
          valA = a.failed_stage || 'zzz'; 
          valB = b.failed_stage || 'zzz';
          break;
        default:
          return 0;
      }

      if (valA < valB) {
        return sortConfig.direction === 'asc' ? -1 : 1;
      }
      if (valA > valB) {
        return sortConfig.direction === 'asc' ? 1 : -1;
      }
      return 0;
    });
  }, [safeItems, sortConfig]);

  // Helper component for sortable headers (Reusable logic)
  const SortableHeader = ({ 
    label, 
    sortKey, 
    tooltip,
    isNumeric = false
  }: { 
    label: string, 
    sortKey: SortKey, 
    tooltip?: string,
    isNumeric?: boolean
  }) => {
    const isActive = sortConfig.key === sortKey;
    const direction = isActive ? sortConfig.direction : null;

    return (
      <Th 
        cursor="pointer" 
        onClick={() => handleSort(sortKey)}
        isNumeric={isNumeric}
        bg={isActive ? activeHeaderBg : undefined}
        _hover={{ bg: activeHeaderBg }}
        userSelect="none"
        transition="background 0.2s"
        whiteSpace="nowrap"
      >
        <Flex align="center" justify={isNumeric ? "flex-end" : "flex-start"}>
          <HStack spacing={1} mr={isNumeric ? 0 : 1} ml={isNumeric ? 1 : 0}>
            {!isNumeric && <Text fontSize="xs" textTransform="uppercase" letterSpacing="wider">{label}</Text>}
            {tooltip && (
              <Tooltip label={tooltip} hasArrow placement="top" fontSize="xs" fontWeight="normal">
                <span role="img" aria-label="info" onClick={(e) => e.stopPropagation()}>
                  <Icon as={Info} size={14} color="gray.400" />
                </span>
              </Tooltip>
            )}
            {isNumeric && <Text fontSize="xs" textTransform="uppercase" letterSpacing="wider">{label}</Text>}
          </HStack>
          
          {direction === 'asc' && <Icon as={ArrowUp} size={14} />}
          {direction === 'desc' && <Icon as={ArrowDown} size={14} />}
          {!direction && <Icon as={ArrowUpDown} size={14} color="gray.400" style={{ opacity: 0.5 }} />}
        </Flex>
      </Th>
    );
  };

  if (safeItems.length === 0) {
    return (
       <Box 
        p={8} 
        textAlign="center" 
        borderWidth="1px" 
        borderRadius="lg" 
        borderColor={borderColor}
        borderStyle="dashed"
        bg={tableBg}
      >
        <Text color="gray.500">No archived items found.</Text>
      </Box>
    );
  }

  const handleDeleteClick = (ticker: string) => {
    if (onDelete && !rowActionsDisabled) {
      onDelete(ticker);
    }
  };

  const handleRestoreClick = (ticker: string) => {
    if (onRestore && !rowActionsDisabled) {
        onRestore(ticker);
    }
  }

  return (
    <TableContainer 
      borderWidth="1px" 
      borderRadius="lg" 
      borderColor={borderColor}
      bg={tableBg}
    >
      <Table variant="simple" size="md">
        <Thead bg={useColorModeValue('gray.50', 'gray.900')}>
          <Tr>
            <SortableHeader label="Ticker" sortKey="ticker" />
            
            <SortableHeader 
              label="Archived At" 
              sortKey="archived_at" 
              tooltip="Date and time when the item was moved to the archive."
            />
            
            <SortableHeader 
              label="Reason" 
              sortKey="reason" 
              tooltip="Why this item was removed (Manual User Action or Failed Automated Check)."
            />
            
            <SortableHeader 
              label="Failed Stage" 
              sortKey="failed_stage" 
              tooltip="If failed health check: The specific step (Screening, VCP, Freshness) that triggered the failure."
            />
            
            <Th textAlign="right">Actions</Th>
          </Tr>
        </Thead>
        <Tbody>
          {sortedItems.map((item) => {
            const { ticker, archived_at, reason, failed_stage } = item;
            const { label, color, icon: StatusIcon } = mapReasonToLabel(reason);
            const failedStageDisplay = failed_stage ?? '-';
            
            // Format date slightly better if it's an ISO string
            const dateDisplay = archived_at 
              ? new Date(archived_at).toLocaleDateString() + ' ' + new Date(archived_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
              : '-';

            return (
              <Tr key={ticker}>
                <Td fontWeight="bold" fontSize="lg">{ticker}</Td>
                <Td fontSize="md" color={dateColor}>{dateDisplay}</Td>
                <Td>
                  <Tag size="md" colorScheme={color} variant="subtle">
                    {StatusIcon && <Icon as={StatusIcon} size={14} mr={1} />}
                    {label}
                  </Tag>
                </Td>
                <Td data-testid={`failed-stage-${ticker}`}>
                  <Text fontSize="md" fontFamily="mono" color={failedStageColor}>
                     {failedStageDisplay}
                  </Text>
                </Td>
                <Td textAlign="right">
                  <HStack justify="flex-end" spacing={1}>
                    {onRestore && (
                        <Tooltip label="Restore to Watchlist" hasArrow>
                            <IconButton
                                aria-label={`Restore ${ticker}`}
                                icon={<Undo2 size={16} />}
                                size="sm"
                                variant="ghost"
                                colorScheme="blue"
                                isDisabled={rowActionsDisabled}
                                onClick={() => handleRestoreClick(ticker)}
                            />
                        </Tooltip>
                    )}
                    <IconButton
                        aria-label={`Delete ${ticker}`}
                        icon={<Trash2 size={16} />}
                        size="sm"
                        colorScheme="red"
                        variant="ghost"
                        isDisabled={rowActionsDisabled || !onDelete}
                        onClick={() => handleDeleteClick(ticker)}
                    />
                  </HStack>
                </Td>
              </Tr>
            );
          })}
        </Tbody>
      </Table>
    </TableContainer>
  );
};