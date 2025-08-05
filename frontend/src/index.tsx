import CssBaseline from '@mui/material/CssBaseline';

import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter, Route, Routes } from 'react-router-dom'
import { initializeIcons } from '@fluentui/react'

import Chat from './pages/chat/Chat'
import Layout from './pages/layout/Layout'
import NoPage from './pages/NoPage'
import AdminPromptsPage from './pages/admin/AdminPromptsPage'
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
          <Route path="/" element={<Layout />}>
            <Route index element={<Chat />} />
            <Route path="*" element={<NoPage />} />

            {/* neue geschützte Admin-Route */}
            <Route
              path="admin/prompts"
              element={
                <RequireAdmin>
                  <AdminPromptProvider>
                    <AdminPromptsPage />
                  </AdminPromptProvider>
                </RequireAdmin>
              }
            />
          </Route>
        </Routes>
      </HashRouter>
    </AppStateProvider>
  )
}

// ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
//   <React.StrictMode>
//     <App />
//   </React.StrictMode>
// )
