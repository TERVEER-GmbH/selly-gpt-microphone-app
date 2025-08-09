import React from 'react'
import { Outlet, Link as RouterLink } from 'react-router-dom'
import {
  AppBar,
  Toolbar,
  IconButton,
  Typography,
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Box,
  Button,
  useTheme,
  styled,
} from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import HomeIcon from '@mui/icons-material/Home'
import LabelIcon from '@mui/icons-material/Label'
import ListAltIcon from '@mui/icons-material/ListAlt'

const drawerWidth = 240

const Main = styled('main', {
  shouldForwardProp: (prop) => prop !== 'open'
})<{ open?: boolean }>(({ theme, open }) => ({
  flexGrow: 1,
  marginTop: theme.spacing(2),

  // default: volle Breite
  width: '100%',
  marginLeft: 0,
  padding: theme.spacing(2),
  transition: theme.transitions.create(['margin','width'], {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),

  // wenn Drawer offen: schiebe und passe Breite an
  ...(open && {
    width: `calc(100% - ${drawerWidth}px)`,
    transition: theme.transitions.create(['margin','width'], {
      easing: theme.transitions.easing.easeOut,
      duration: theme.transitions.duration.enteringScreen,
    }),
  }),
}))

export default function AdminLayout() {
  const theme = useTheme()
  // Drawer initial ausgeklappt
  const [open, setOpen] = React.useState(true)

  const toggleDrawer = () => {
    setOpen(prev => !prev)
  }

  return (
    <Box sx={{ display: 'flex' }}>
      {/* AppBar */}
      <AppBar position="fixed" color="primary" sx={{ zIndex: theme.zIndex.drawer + 1 }}>
        <Toolbar>
          <IconButton
            edge="start"
            color="inherit"
            onClick={toggleDrawer}
            sx={{ mr: 2 }}
          >
            {open ? <ChevronLeftIcon /> : <MenuIcon />}
          </IconButton>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Admin Panel
          </Typography>
          <Button
            component={RouterLink}
            to="/"
            variant="outlined"
            color="inherit"
            startIcon={<HomeIcon />}
          >
            Back to Chat
          </Button>
        </Toolbar>
      </AppBar>

      {/* Persistent Drawer */}
      <Drawer
        variant="persistent"
        anchor="left"
        open={open}
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: drawerWidth,
            boxSizing: 'border-box',
          },
        }}
      >
        {/* Toolbar-Puffer */}
        <Toolbar />

        <List>
          <ListItemButton component={RouterLink} to="prompts">
            <ListItemIcon><LabelIcon /></ListItemIcon>
            <ListItemText primary="Prompts" />
          </ListItemButton>
          <ListItemButton component={RouterLink} to="runs">
            <ListItemIcon><ListAltIcon /></ListItemIcon>
            <ListItemText primary="Runs" />
          </ListItemButton>
        </List>
      </Drawer>

      {/* Haupt-Inhalt */}
      <Main open={open}>
        {/* Toolbar-Puffer */}
        {/* <Toolbar /> */}
        <Outlet />
      </Main>
    </Box>
  )
}
