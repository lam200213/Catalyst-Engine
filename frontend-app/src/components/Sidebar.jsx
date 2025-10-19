// frontend-app/src/components/Sidebar.jsx

import React from 'react';
import { Box, VStack, Link, Text, Icon } from '@chakra-ui/react';
import { NavLink } from 'react-router-dom';
import { MdDashboard, MdAssessment, MdVisibility, MdWork } from 'react-icons/md';

const NavItem = ({ to, icon, children }) => (
    <Link
        as={NavLink}
        to={to}
        display="flex"
        alignItems="center"
        p={3}
        borderRadius="md"
        w="100%"
        _hover={{ bg: 'gray.600' }}
        _activeLink={{ bg: 'blue.500', color: 'white' }}
    >
        <Icon as={icon} mr={3} />
        <Text>{children}</Text>
    </Link>
);

const Sidebar = () => {
    return (
        <Box
            as="nav"
            pos="sticky"
            top="0"
            h="100vh"
            w={{ base: '60px', md: '240px' }}
            bg="gray.800"
            p={4}
            color="white"
        >
            <VStack align="stretch" spacing={2}>
                <NavItem to="/" icon={MdDashboard}>Dashboard</NavItem>
                <NavItem to="/market" icon={MdAssessment}>Market</NavItem>
                <NavItem to="/watchlist" icon={MdVisibility}>Watchlist</NavItem>
                <NavItem to="/portfolio" icon={MdWork}>Portfolio</NavItem>
            </VStack>
        </Box>
    );
};

export default Sidebar;