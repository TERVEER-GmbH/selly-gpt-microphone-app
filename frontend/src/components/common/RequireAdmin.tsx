import React, { useContext } from 'react'
import { Navigate } from 'react-router-dom'
import { AppStateContext } from '../../state/AppProvider'
import Spinner from '../ui/spinner'  // oder wie auch immer Dein Loader heißt

interface RequireAdminProps {
  children: React.ReactNode
}

export const RequireAdmin: React.FC<RequireAdminProps> = ({ children }) => {
  const ctx = useContext(AppStateContext)
  if (!ctx) {
    throw new Error('AppStateContext nicht gefunden')
  }
  const { state } = ctx

  // noch am Laden? Spinner anzeigen
  if (state.isLoading) {
    return <Spinner />
  }

  // kein Admin? zurück zur Startseite
  if (!state.isAdmin) {
    return <Navigate to="/" replace />
  }

  // alles gut? zeige die Kinder (Admin-Seite)
  return <>{children}</>
}
