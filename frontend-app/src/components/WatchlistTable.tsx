// frontend-app/src/components/WatchlistTable.tsx
import React, { useMemo, useState } from 'react';
import {
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  TableContainer,
  Checkbox,
  Badge,
  IconButton,
  Tooltip,
  Text,
  HStack,
  Icon,
  Box,
  useColorModeValue,
  Flex,
} from '@chakra-ui/react';
import { 
  Star, 
  Trash2, 
  TrendingUp, 
  AlertTriangle, 
  ArrowUpDown, 
  ArrowUp, 
  ArrowDown,
  Info
} from 'lucide-react';
import type { WatchlistItem } from '../types/monitoring';

export interface WatchlistTableProps {
  items?: WatchlistItem[] | null;
  selectedTickers?: string[];
  onToggleSelect?: (ticker: string) => void;
  onRemoveSelected?: () => void;
  onToggleFavourite?: (ticker: string, is_favourite: boolean) => void;
  onRemoveItem?: (ticker: string) => void;
  rowActionsDisabled?: boolean;
}

// --- Sorting Types & Weights ---

type SortKey = 
  | 'ticker' 
  | 'status' 
  | 'health' 
  | 'pivot' 
  | 'vol' 
  | 'price' 
  | 'change' 
  | 'vcp' 
  | 'age';

type SortDirection = 'asc' | 'desc';

interface SortConfig {
  key: SortKey;
  direction: SortDirection;
}

// Weighted rank for Status (lower number = higher priority)
const STATUS_RANK: Record<string, number> = {
  'Buy Ready': 1,
  'Buy Alert': 2,
  'Watch': 3,
  'Pending': 4,
  'Failed': 5,
};

// Weighted rank for Health
const HEALTH_RANK: Record<string, number> = {
  'PASS': 1,
  'PENDING': 2,
  'UNKNOWN': 3,
  'FAIL': 4,
};

const getStatusBadgeProps = (status: string | undefined) => {
  switch (status) {
    case 'Buy Ready':
      return { colorScheme: 'green', variant: 'solid' };
    case 'Buy Alert':
      return { colorScheme: 'yellow', variant: 'subtle' };
    case 'Watch':
      return { colorScheme: 'blue', variant: 'outline' };
    default:
      return { colorScheme: 'gray', variant: 'outline' };
  }
};

const getHealthBadgeColor = (health: string | undefined): string => {
  switch (health) {
    case 'PASS':
      return 'green';
    case 'FAIL':
      return 'red';
    case 'PENDING':
      return 'yellow';
    case 'UNKNOWN':
    default:
      return 'gray';
  }
};

export const WatchlistTable: React.FC<WatchlistTableProps> = ({
  items,
  selectedTickers = [],
  onToggleSelect,
  onRemoveSelected,
  onToggleFavourite,
  onRemoveItem,
  rowActionsDisabled = false,
}) => {
  const safeItems = Array.isArray(items) ? items : [];
  
  // Theme hooks
  const tableBg = useColorModeValue('white', 'gray.800');
  const hoverBg = useColorModeValue('gray.50', 'gray.700');
  const borderColor = useColorModeValue('gray.200', 'gray.700');
  const activeHeaderBg = useColorModeValue('gray.100', 'gray.700');

  // Sorting State
  const [sortConfig, setSortConfig] = useState<SortConfig | null>(null);

  // Sorting Handler
  const handleSort = (key: SortKey) => {
    let direction: SortDirection = 'asc';
    
    // Default to 'desc' (Highest/Best first) for numeric metrics usually
    if (['vol', 'pivot', 'price', 'change'].includes(key)) {
         direction = 'desc'; 
    }

    // Toggle logic
    if (sortConfig && sortConfig.key === key) {
        direction = sortConfig.direction === 'asc' ? 'desc' : 'asc';
    }
    
    setSortConfig({ key, direction });
  };

  // Memoized Sorted Items
  const sortedItems = useMemo(() => {
    const data = [...safeItems];

    return data.sort((a, b) => {
      // 1. No Active Sort: "Pinned" mode (Favourites top, then Ticker)
      if (!sortConfig) {
        if (a.is_favourite && !b.is_favourite) return -1;
        if (!a.is_favourite && b.is_favourite) return 1;
        return a.ticker.localeCompare(b.ticker);
      }

      // 2. Active Sort Logic
      let valA: any;
      let valB: any;

      switch (sortConfig.key) {
        case 'ticker':
          valA = a.ticker;
          valB = b.ticker;
          break;
        case 'status':
          // Map string status to numeric rank for sorting
          valA = STATUS_RANK[a.status] || 99;
          valB = STATUS_RANK[b.status] || 99;
          break;
        case 'health':
          valA = HEALTH_RANK[a.last_refresh_status] || 99;
          valB = HEALTH_RANK[b.last_refresh_status] || 99;
          break;
        case 'pivot':
          // Handle nulls by treating them as infinity so they go to bottom
          valA = typeof a.pivot_proximity_percent === 'number' ? a.pivot_proximity_percent : -999999;
          valB = typeof b.pivot_proximity_percent === 'number' ? b.pivot_proximity_percent : -999999;
          break;
        case 'vol':
          valA = typeof a.vol_vs_50d_ratio === 'number' ? a.vol_vs_50d_ratio : -1;
          valB = typeof b.vol_vs_50d_ratio === 'number' ? b.vol_vs_50d_ratio : -1;
          break;
        case 'price':
            valA = typeof a.current_price === 'number' ? a.current_price : -1;
            valB = typeof b.current_price === 'number' ? b.current_price : -1;
            break;
        case 'change':
            valA = typeof a.day_change_pct === 'number' ? a.day_change_pct : -999;
            valB = typeof b.day_change_pct === 'number' ? b.day_change_pct : -999;
            break;
        case 'vcp':
             valA = a.vcpFootprint || '';
             valB = b.vcpFootprint || '';
             break;
        case 'age':
             // Sort by days (numeric). Nulls to bottom (-1)
             valA = typeof a.pattern_age_days === 'number' ? a.pattern_age_days : -1;
             valB = typeof b.pattern_age_days === 'number' ? b.pattern_age_days : -1;
             break;
        default:
          return 0;
      }

      // Primary Comparison (Direction dependent)
      if (valA < valB) {
        return sortConfig.direction === 'asc' ? -1 : 1;
      }
      if (valA > valB) {
        return sortConfig.direction === 'asc' ? 1 : -1;
      }

      // --- TIE BREAKERS (Values are equal) ---
      
      // Secondary: Favourites first (Always on top of the group, ignoring sort direction)
      if (a.is_favourite && !b.is_favourite) return -1;
      if (!a.is_favourite && b.is_favourite) return 1;

      // Tertiary: Ticker alpha (Stable fallback)
      return a.ticker.localeCompare(b.ticker);
    });

  }, [safeItems, sortConfig]);


  // Helper component for sortable headers
  const SortableHeader = ({ 
    label, 
    sortKey, 
    isNumeric = false, 
    tooltip 
  }: { 
    label: string, 
    sortKey: SortKey, 
    isNumeric?: boolean, 
    tooltip?: string 
  }) => {
    const isActive = sortConfig?.key === sortKey;
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
          {/* Label + Tooltip for Left Aligned */}
          {!isNumeric && (
            <HStack spacing={1} mr={1}>
              <Text>{label}</Text>
              {tooltip && (
                <Tooltip label={tooltip} hasArrow placement="top" fontSize="xs" fontWeight="normal">
                  <span role="img" aria-label="info" onClick={(e) => e.stopPropagation()}>
                    <Icon as={Info} size={14} color="gray.400" />
                  </span>
                </Tooltip>
              )}
            </HStack>
          )}
          
          {/* Sort Icons */}
          {direction === 'asc' && <Icon as={ArrowUp} size={14} />}
          {direction === 'desc' && <Icon as={ArrowDown} size={14} />}
          {!direction && <Icon as={ArrowUpDown} size={14} color="gray.400" style={{ opacity: 0.5 }} />}
          
          {/* Label + Tooltip for Right Aligned */}
          {isNumeric && (
            <HStack spacing={1} ml={1}>
              {tooltip && (
                <Tooltip label={tooltip} hasArrow placement="top" fontSize="xs" fontWeight="normal">
                  <span role="img" aria-label="info" onClick={(e) => e.stopPropagation()}>
                    <Icon as={Info} size={14} color="gray.400" />
                  </span>
                </Tooltip>
              )}
              <Text>{label}</Text>
            </HStack>
          )}
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
        <Text fontSize="lg" fontWeight="medium" mb={1}>Your watchlist is empty.</Text>
        <Text color="gray.500">Add a ticker to start tracking.</Text>
      </Box>
    );
  }

  const handleCheckboxChange = (ticker: string) => {
    if (onToggleSelect) {
      onToggleSelect(ticker);
    }
  };

  const handleFavouriteClick = (ticker: string, currentIsFavourite: boolean) => {
    if (!onToggleFavourite || rowActionsDisabled) {
      return;
    }
    onToggleFavourite(ticker, !currentIsFavourite);
  };

  const handleDeleteClick = (ticker: string) => {
    if (!onRemoveItem || rowActionsDisabled) {
      return;
    }
    onRemoveItem(ticker);
  };

  const isTickerSelected = (ticker: string): boolean =>
    Array.isArray(selectedTickers) ? selectedTickers.includes(ticker) : false;

  return (
    <TableContainer 
      borderWidth="1px" 
      borderRadius="lg" 
      borderColor={borderColor}
      bg={tableBg}
      overflowX="auto"
    >
      <Table variant="simple" size="sm">
        <Thead bg={useColorModeValue('gray.50', 'gray.900')}>
          <Tr>
            <Th width="40px" px={4} />
            <SortableHeader label="Ticker" sortKey="ticker" />
            
            <SortableHeader 
              label="Status" 
              sortKey="status" 
              tooltip="Derived status: 'Buy Ready' (Actionable), 'Buy Alert' (Setup forming), 'Watch' (Valid)."
            />
            
            <SortableHeader label="Price" sortKey="price" isNumeric />
            <SortableHeader label="Change" sortKey="change" isNumeric />
            
            <SortableHeader 
              label="Pivot" 
              sortKey="pivot" 
              isNumeric 
              tooltip="The actionable price point (VCP breakout level), with % distance to current price."
            />
            
            <SortableHeader 
              label="Vol vs 50D" 
              sortKey="vol" 
              isNumeric 
              tooltip="Volume Ratio: Current Volume / 50-Day Average. >1.0x indicates above-average activity."
            />
            
            <SortableHeader 
              label="VCP" 
              sortKey="vcp" 
              tooltip="Volatility Contraction Pattern footprint (Weeks | Depth | Tightness)."
            />
            
            <SortableHeader 
              label="Age" 
              sortKey="age" 
              isNumeric 
              tooltip="Days since the VCP pivot point was formed. Patterns >90 days may be stale."
            />
            
            <Th>Flags</Th>
            
            <SortableHeader 
              label="Health" 
              sortKey="health" 
              tooltip="Latest automated health check result (Screening -> VCP -> Freshness)."
            />
            
            <Th width="80px" textAlign="right">Actions</Th>
          </Tr>
        </Thead>
        <Tbody>
          {sortedItems.map((item) => {
            const {
              ticker,
              status,
              last_refresh_status,
              is_favourite,
              is_leader,
              is_at_pivot,
              has_pullback_setup,
              pivot_price,
              pivot_proximity_percent,
              vol_vs_50d_ratio,
              day_change_pct,
              current_price,
              vcpFootprint,
              pattern_age_days
            } = item;

            const statusProps = getStatusBadgeProps(status);
            
            const statusTestColor = 
              status === 'Buy Ready' ? 'green' : 
              status === 'Buy Alert' ? 'yellow' : 
              status === 'Watch' ? 'blue' : 'gray';

            const healthColor = getHealthBadgeColor(last_refresh_status);

            const volRatio = typeof vol_vs_50d_ratio === 'number' ? vol_vs_50d_ratio : null;
            const isPositiveDay = typeof day_change_pct === 'number' ? day_change_pct > 0 : false;
            const volColor = isPositiveDay ? 'green.400' : 'red.400';
            const volTestColor = isPositiveDay ? 'green' : 'red';
            const isSpike = volRatio !== null && volRatio >= 3;
            const volFontWeight = isSpike ? 'bold' : 'normal';

            return (
              <Tr key={ticker} _hover={{ bg: hoverBg }} transition="background 0.2s">
                <Td px={4}>
                  <Checkbox
                    aria-label={`select ${ticker}`}
                    isChecked={isTickerSelected(ticker)}
                    isDisabled={!onToggleSelect}
                    onChange={() => handleCheckboxChange(ticker)}
                    colorScheme="blue"
                  />
                </Td>
                <Td fontWeight="semibold">
                  <HStack spacing={2}>
                    <Text>{ticker}</Text>
                    {is_leader && (
                      <Tooltip label="Leadership Stock" hasArrow>
                        <span aria-label={`Leadership stock ${ticker}`}>
                           <Icon as={TrendingUp} color="yellow.400" w={4} h={4} />
                        </span>
                      </Tooltip>
                    )}
                  </HStack>
                </Td>
                <Td>
                  <Badge
                    {...statusProps}
                    data-testid={`status-badge-${ticker}`}
                    data-color={statusTestColor}
                    px={2}
                    py={0.5}
                    borderRadius="full"
                  >
                    {status}
                  </Badge>
                </Td>
                
                {/* Price Column */}
                <Td isNumeric>
                  {typeof current_price === 'number' 
                    ? current_price.toFixed(2) 
                    : '-'}
                </Td>

                {/* Change % Column */}
                <Td isNumeric>
                   {typeof day_change_pct === 'number' ? (
                       <Text 
                         color={day_change_pct > 0 ? 'green.400' : day_change_pct < 0 ? 'red.400' : 'inherit'}
                         fontWeight="medium"
                       >
                         {day_change_pct > 0 ? '+' : ''}{day_change_pct.toFixed(2)}%
                       </Text>
                   ) : '-'}
                </Td>

                {/* Pivot Column */}
                <Td isNumeric data-testid={`pivot-cell-${ticker}`}>
                  {typeof pivot_price === 'number' && (
                    <Box lineHeight="1.1">
                      <Text fontSize="sm">{pivot_price.toFixed(2)}</Text>
                      {typeof pivot_proximity_percent === 'number' && (
                        <Text 
                          fontSize="xs" 
                          color={pivot_proximity_percent >= 0 ? 'green.400' : 'red.400'}
                        >
                          ({pivot_proximity_percent > 0 ? '+' : ''}{pivot_proximity_percent.toFixed(2)}%)
                        </Text>
                      )}
                    </Box>
                  )}
                </Td>

                {/* Vol vs 50D Column */}
                <Td 
                  isNumeric
                  data-testid={`vol-cell-${ticker}`}
                  data-color={volTestColor}
                  data-highlight={isSpike ? 'true' : undefined}
                  color={volRatio !== null ? volColor : 'inherit'}
                  fontWeight={volFontWeight}
                >
                  {volRatio !== null ? (
                    <HStack justify="flex-end" spacing={1}>
                       {isSpike && <Icon as={AlertTriangle} color="yellow.400" w={3} h={3} />}
                       <Text>{volRatio.toFixed(1)}x</Text>
                    </HStack>
                  ) : '-'}
                </Td>

                {/* VCP Footprint Column */}
                <Td maxW="150px" overflow="hidden" textOverflow="ellipsis" whiteSpace="nowrap">
                    <Tooltip label={vcpFootprint} hasArrow isDisabled={!vcpFootprint}>
                        <Text fontSize="xs" color="gray.500">
                            {vcpFootprint || '-'}
                        </Text>
                    </Tooltip>
                </Td>

                {/* Pattern Age (Days) Column */}
                <Td isNumeric>
                    {typeof pattern_age_days === 'number' ? (
                         <Text fontSize="sm">{pattern_age_days}d</Text>
                    ) : '-'}
                </Td>

                {/* Flags Column (Moved to Right) */}
                <Td>
                  <HStack spacing={1}>
                    {is_at_pivot && (
                      <Tooltip label="Price is currently at or near the actionable pivot buy point." hasArrow>
                        <Badge colorScheme="purple" fontSize="0.65rem">PIVOT</Badge>
                      </Tooltip>
                    )}
                    {has_pullback_setup && (
                      <Tooltip label="Pullback Setup: Strong trend, extended above pivot, valid base. Watch for low-volume dip." hasArrow>
                        <Badge colorScheme="cyan" fontSize="0.65rem">PB</Badge>
                      </Tooltip>
                    )}
                  </HStack>
                </Td>

                {/* Health Column (Moved to Right) */}
                <Td>
                  <Badge
                    colorScheme={healthColor === 'gray' ? 'gray' : healthColor}
                    variant="subtle"
                    data-testid={`health-badge-${ticker}`}
                    data-color={healthColor}
                    fontSize="xs"
                  >
                    {last_refresh_status}
                  </Badge>
                </Td>

                {/* Actions Column (Far Right) */}
                <Td textAlign="right">
                  <HStack justify="flex-end" spacing={1}>
                    <IconButton
                      aria-label={`Favourite stock ${ticker}`}
                      icon={<Star fill={is_favourite ? "currentColor" : "none"} />}
                      size="sm"
                      variant="ghost"
                      colorScheme={is_favourite ? "yellow" : "gray"}
                      isDisabled={rowActionsDisabled}
                      onClick={() => handleFavouriteClick(ticker, Boolean(is_favourite))}
                    />
                    <IconButton
                      aria-label={`Delete ${ticker}`}
                      icon={<Trash2 size={16} />}
                      size="sm"
                      variant="ghost"
                      colorScheme="red"
                      isDisabled={rowActionsDisabled || !onRemoveItem}
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