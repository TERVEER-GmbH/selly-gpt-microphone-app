// src/pages/admin/RunsOverviewPage.tsx
import React, { useEffect, useState } from 'react'
import {
  Container,
  Typography,
  Stack,
  Button,
  TableContainer,
  Paper,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  CircularProgress,
  Alert
} from '@mui/material'
import { useNavigate } from 'react-router-dom'
import type { RunSummary } from '../../api/models'
import { getRuns } from '../../api/api'

const RunsOverviewPage: React.FC = () => {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const loadRuns = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getRuns()
      setRuns(data)
    } catch (err: any) {
      console.error(err)
      setError(err.message || 'Fehler beim Laden der Runs')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadRuns()
  }, [])

  return (
    <Container sx={{ mt: 4, mb: 4 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h4">Übersicht aller Test-Runs</Typography>
        <Button variant="outlined" onClick={loadRuns} disabled={loading}>
          {loading ? <CircularProgress size={20} /> : 'Aktualisieren'}
        </Button>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {loading && !runs.length ? (
        <Stack alignItems="center" pt={4}>
          <CircularProgress />
        </Stack>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Run ID</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Erstellt am</TableCell>
                <TableCell align="right">Prompts</TableCell>
                <TableCell align="right">Fertig</TableCell>
                <TableCell align="right">Aktion</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {runs.map(run => (
                <TableRow key={run.id} hover>
                  <TableCell>{run.id}</TableCell>
                  <TableCell>{run.status}</TableCell>
                  <TableCell>{new Date(run.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right">{run.prompt_ids.length}</TableCell>
                  <TableCell align="right">
                    {/* completed wird hier on the fly im Backend berechnet */}
                    {run.status === 'Done'
                      ? run.prompt_ids.length
                      : '—'}
                  </TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => navigate(`/admin/runs/${run.id}`)}
                    >
                      Details
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {runs.length === 0 && !loading && (
                <TableRow>
                  <TableCell colSpan={6} align="center">
                    Keine Runs gefunden.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Container>
  )
}

export default RunsOverviewPage
