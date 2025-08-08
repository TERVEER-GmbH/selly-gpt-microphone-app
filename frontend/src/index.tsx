import CssBaseline from '@mui/material/CssBaseline';

import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter, Route, Routes, Navigate, Outlet } from 'react-router-dom'
import { initializeIcons } from '@fluentui/react'

import Chat from './pages/chat/Chat'
import Layout from './pages/layout/Layout'
import NoPage from './pages/NoPage'
import AdminPromptsPage from './pages/admin/AdminPromptsPage'
import RunsOverviewPage from './pages/admin/RunsOverviewPage'
import RunDetailPage from './pages/admin/RunDetailPage'

import AdminLayout from './components/admin/AdminLayout'

import { RequireAdmin }   from './components/common/RequireAdmin'

import { AppStateProvider } from './state/AppProvider'
import { AdminPromptProvider } from './state/AdminPromptContext'

import './index.css'

import '@fontsource/roboto/300.css';
import '@fontsource/roboto/400.css';
import '@fontsource/roboto/500.css';
import '@fontsource/roboto/700.css';

const container = document.getElementById('root')
if (!container) {
  throw new Error('Could not find root container')
}

const root = ReactDOM.createRoot(container)
root.render(
  <React.StrictMode>
    <CssBaseline />
    <App />
  </React.StrictMode>
)

initializeIcons("https://res.cdn.office.net/files/fabric-cdn-prod_20241209.001/assets/icons/")

export default function App() {
  return (
    <AppStateProvider>
      <HashRouter>
        <Routes>
          {/* öffentlicher Bereich */}
          <Route path="/" element={<Layout />}>
            {/* Chat‐Startseite */}
            <Route index element={<Chat />} />

            {/* Admin‐Bereich, geschützt */}
            <Route
              path="admin"
              element={
                <RequireAdmin>
                  <AdminLayout />
                </RequireAdmin>
              }
            >
              {/* Default‐Redirect von /#/admin → /#/admin/prompts */}
              <Route index element={<Navigate to="prompts" replace />} />

              {/* /#/admin/prompts */}
              <Route
                path="prompts"
                element={
                  <AdminPromptProvider>
                    <AdminPromptsPage />
                  </AdminPromptProvider>
                }
              />

              {/* /#/admin/runs */}
              <Route path="runs" element={<RunsOverviewPage />} />

              {/* /#/admin/runs/:runId */}
              <Route path="runs/:runId" element={<RunDetailPage />} />
            </Route>

            {/* Fallback */}
            <Route path="*" element={<NoPage />} />
          </Route>
        </Routes>
      </HashRouter>
    </AppStateProvider>
  )
}
