// src/pages/layout/Layout.tsx
import React, { useContext, useEffect, useState } from 'react'
import { Link, Outlet } from 'react-router-dom'
import {
  AppBar,
  Toolbar,
  IconButton,
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  TextField,
  Typography,
  useMediaQuery,
  useTheme
} from '@mui/material'
import HistoryIcon from '@mui/icons-material/History'
import ShareIcon   from '@mui/icons-material/Share'
import AdminIcon   from '@mui/icons-material/AdminPanelSettings'
import CopyIcon    from '@mui/icons-material/ContentCopy'

import { AppStateContext } from '../../state/AppProvider'
import ContosoLogo        from '../../assets/Contoso.svg'
import { CosmosDBStatus } from '../../api'

const Layout: React.FC = () => {
  const { state, dispatch } = useContext(AppStateContext)!
  const theme    = useTheme()
  const isSmall  = useMediaQuery(theme.breakpoints.down('sm'))

  const [shareOpen, setShareOpen] = useState(false)
  const [copied,    setCopied]    = useState(false)
  const [logo,      setLogo]      = useState('')

  useEffect(() => {
    if (!state.isLoading) {
      setLogo(state.frontendSettings?.ui?.logo || ContosoLogo)
    }
  }, [state.isLoading, state.frontendSettings])

  const toggleHistory = () => dispatch({ type: 'TOGGLE_CHAT_HISTORY' })
  const openShare     = () => setShareOpen(true)
  const closeShare    = () => { setShareOpen(false); setCopied(false) }
  const doCopy        = () => { navigator.clipboard.writeText(window.location.href); setCopied(true) }

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',      // Gesamt-Viewport ausfüllen
      }}
    >
      {/* Header */}
      <AppBar position="static" color="default" elevation={1}>
        <Toolbar>
          <Box display="flex" alignItems="center" flexGrow={1}>
            <Link to="/">
              <Box component="img" src={logo} alt="Logo" sx={{ height: 32, mr: 2 }} />
            </Link>
            <Typography
              variant="h6"
              component={Link}
              to="/"
              sx={{ textDecoration: 'none', color: 'inherit', fontWeight: 600 }}
            >
              {state.frontendSettings?.ui?.title}
            </Typography>
          </Box>

          {state.isCosmosDBAvailable.status !== CosmosDBStatus.NotConfigured &&
           state.frontendSettings?.ui?.show_chat_history_button && (
            <IconButton color="inherit" onClick={toggleHistory} sx={{ mr: 1 }}>
              <HistoryIcon />
              {!isSmall && (
                <Typography variant="button" sx={{ ml: 0.5 }}>
                  {state.isChatHistoryOpen ? 'Hide History' : 'Show History'}
                </Typography>
              )}
            </IconButton>
          )}

          {state.isAdmin && (
            <Button
              component={Link}
              to="/admin/prompts"
              variant="contained"
              color="primary"
              startIcon={<AdminIcon />}
              sx={{ textTransform: 'none', mr: 1 }}
            >
              {!isSmall && 'Admin Portal'}
            </Button>
          )}

          {state.frontendSettings?.ui?.show_share_button && (
            <IconButton color="inherit" onClick={openShare}>
              <ShareIcon />
              {!isSmall && (
                <Typography variant="button" sx={{ ml: 0.5 }}>
                  Share
                </Typography>
              )}
            </IconButton>
          )}
        </Toolbar>
      </AppBar>

      {/* Content-Bereich */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,            // füllt den Rest nach Header und ggf. Footer
          display: 'flex',
          flexDirection: 'column',
          overflow: 'auto',
          bgcolor: 'background.default',
          p: 2
        }}
      >
        <Outlet />
      </Box>

      {/* Share-Dialog */}
      <Dialog open={shareOpen} onClose={closeShare} fullWidth maxWidth="sm">
        <DialogTitle>Share the web app</DialogTitle>
        <DialogContent>
          <Box display="flex" alignItems="center" mt={1}>
            <TextField
              fullWidth
              value={window.location.href}
              InputProps={{ readOnly: true }}
            />
            <IconButton onClick={doCopy} sx={{ ml: 1 }}>
              <CopyIcon />
            </IconButton>
            {!isSmall && (
              <Typography variant="button" sx={{ ml: 1 }}>
                {copied ? 'Copied!' : 'Copy URL'}
              </Typography>
            )}
          </Box>
        </DialogContent>
      </Dialog>
    </Box>
  )
}

export default Layout
