// src/components/admin/AdminLayout.tsx
import React from 'react'
import { Outlet, Link as RouterLink, useLocation, useMatch, useResolvedPath } from 'react-router-dom'
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
  useMediaQuery,
} from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import HomeIcon from '@mui/icons-material/Home'
import LabelOutlinedIcon from '@mui/icons-material/LabelOutlined'
import ListAltOutlinedIcon from '@mui/icons-material/ListAltOutlined'
import CompareArrowsOutlinedIcon from '@mui/icons-material/CompareArrowsOutlined'

const drawerWidth = 240

const Main = styled('main', {
  shouldForwardProp: (prop) => prop !== 'open' && prop !== 'hasPersistentDrawer'
})<{ open?: boolean; hasPersistentDrawer?: boolean }>(({ theme, open, hasPersistentDrawer }) => ({
  flexGrow: 1,
  width: '100%',
  padding: theme.spacing(2),
  transition: theme.transitions.create(['margin','width'], {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  ...(open && hasPersistentDrawer && {
    width: `calc(100% - ${drawerWidth}px)`,
    transition: theme.transitions.create(['margin','width'], {
      easing: theme.transitions.easing.easeOut,
      duration: theme.transitions.duration.enteringScreen,
    }),
  }),
}))

function NavListItem({
  to,
  icon,
  label,
  onClick,
  end = false, // end=true für exakten Match
}: {
  to: string
  icon: React.ReactNode
  label: string
  onClick?: () => void
  end?: boolean
}) {
  const resolved = useResolvedPath(to)
  const match = useMatch({ path: resolved.pathname, end })
  const selected = Boolean(match)

  return (
    <ListItemButton
      component={RouterLink}
      to={to}
      onClick={onClick}
      selected={selected}
      sx={{
        '&.Mui-selected': {
          bgcolor: (t) => t.palette.action.selected,
        },
      }}
    >
      <ListItemIcon>{icon}</ListItemIcon>
      <ListItemText primary={label} />
    </ListItemButton>
  )
}

export default function AdminLayout() {
  const theme = useTheme()
  const isMdUp = useMediaQuery(theme.breakpoints.up('md'))
  const [open, setOpen] = React.useState<boolean>(isMdUp)

  React.useEffect(() => {
    setOpen(isMdUp)
  }, [isMdUp])

  const toggleDrawer = () => setOpen((p) => !p)
  const location = useLocation()

  const title = React.useMemo(() => {
    if (location.pathname.includes('/admin/prompts')) return 'Prompts'
    if (location.pathname.includes('/admin/runs')) return 'Runs'
    if (location.pathname.includes('/admin/compare')) return 'A/B Vergleich'
    return 'Admin Panel'
  }, [location.pathname])

  const drawerContent = (
    <>
      <Toolbar />
      <List>
        <NavListItem to="/admin/prompts" icon={<LabelOutlinedIcon />} label="Prompts" onClick={!isMdUp ? toggleDrawer : undefined} />
        <NavListItem to="/admin/runs" icon={<ListAltOutlinedIcon />} label="Runs" onClick={!isMdUp ? toggleDrawer : undefined} />
        <NavListItem to="/admin/compare" icon={<CompareArrowsOutlinedIcon />} label="A/B Vergleich" onClick={!isMdUp ? toggleDrawer : undefined} />
      </List>
    </>
  )

  return (
    <Box sx={{ display: 'flex' }}>
      <AppBar position="fixed" color="primary" sx={{ zIndex: theme.zIndex.drawer + 1 }}>
        <Toolbar>
          <IconButton edge="start" color="inherit" onClick={toggleDrawer} sx={{ mr: 2 }}>
            {open && isMdUp ? <ChevronLeftIcon /> : <MenuIcon />}
          </IconButton>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            {title}
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

      <Drawer
        variant={isMdUp ? 'persistent' : 'temporary'}
        anchor="left"
        open={open}
        onClose={!isMdUp ? toggleDrawer : undefined}
        ModalProps={{ keepMounted: true }}
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: drawerWidth,
            boxSizing: 'border-box',
          },
        }}
      >
        {drawerContent}
      </Drawer>

      <Main open={open} hasPersistentDrawer={isMdUp}>
        <Toolbar />
        <Outlet />
      </Main>
    </Box>
  )
}
