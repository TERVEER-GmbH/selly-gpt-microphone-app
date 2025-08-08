// src/pages/admin/RunDetailPage.tsx
import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Container,
  Stack,
  Typography,
  Button,
  CircularProgress,
  Alert,
  TableContainer,
  Paper,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody
} from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import type { RunStatus, TestResult } from '../../api/models'
import { getRunStatus, getRunResults } from '../../api/api'

const RunDetailPage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()

  const [status, setStatus] = useState<RunStatus | null>(null)
  const [results, setResults] = useState<TestResult[]>([])
  const [loadingStatus, setLoadingStatus] = useState<boolean>(false)
  const [loadingResults, setLoadingResults] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  // Polling für den Run-Status
  useEffect(() => {
    if (!runId) return
    let timer: ReturnType<typeof setTimeout>

    const fetchStatus = async () => {
      setLoadingStatus(true)
      try {
        const s = await getRunStatus(runId)
        setStatus(s)
        // solange noch nicht fertig, weiter pollen
        if (s.status !== 'Done') {
          timer = setTimeout(fetchStatus, 2000)
        } else {
          // wenn Done, Ergebnisse laden
          loadResults()
        }
      } catch (e: any) {
        console.error(e)
        setError('Fehler beim Laden des Run-Status')
      } finally {
        setLoadingStatus(false)
      }
    }

    fetchStatus()
    return () => clearTimeout(timer)
  }, [runId])

  // Ergebnisse laden
  const loadResults = async () => {
    if (!runId) return
    setLoadingResults(true)
    try {
      const res = await getRunResults(runId)
      setResults(res)
    } catch (e: any) {
      console.error(e)
      setError('Fehler beim Laden der Ergebnisse')
    } finally {
      setLoadingResults(false)
    }
  }

  if (!runId) {
    return (
      <Container sx={{ mt: 4 }}>
        <Alert severity="error">Keine Run-ID gefunden.</Alert>
      </Container>
    )
  }

  return (
    <Container sx={{ mt: 4, mb: 4 }}>
      <Stack direction="row" alignItems="center" spacing={2} mb={3}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate(-1)}
        >
          Zurück
        </Button>
        <Typography variant="h5">
          Run Details: {runId}
        </Typography>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
        <Typography variant="subtitle1"><strong>Status:</strong>{' '}
          {loadingStatus
            ? <CircularProgress size={16} />
            : status?.status}
        </Typography>
        {status && (
          <>
            <Typography variant="body2">
              <strong>Erstellt am:</strong>{' '}
              {new Date(status.created_at).toLocaleString()}
            </Typography>
            <Typography variant="body2">
              <strong>Prompts total:</strong>{' '}
              {status.total}
            </Typography>
            <Typography variant="body2">
              <strong>Erledigt:</strong>{' '}
              {status.completed} / {status.total}
            </Typography>
          </>
        )}
      </Paper>

      <Typography variant="h6" gutterBottom>
        Ergebnisse
      </Typography>

      {loadingResults
        ? (
          <Stack alignItems="center" pt={4}>
            <CircularProgress />
          </Stack>
        )
        : (
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Prompt</TableCell>
                  <TableCell>AI-Antwort</TableCell>
                  <TableCell>Golden Answer</TableCell>
                  <TableCell>Timestamp</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {results.map(r => (
                  <TableRow key={r.id} hover>
                    <TableCell sx={{ maxWidth: 200, whiteSpace: 'normal', wordBreak: 'break-word' }}>
                      {r.prompt_text}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 200, whiteSpace: 'normal', wordBreak: 'break-word' }}>
                      {r.ai_response}
                    </TableCell>
                    <TableCell>{r.golden_answer}</TableCell>
                    <TableCell>
                      {new Date(r.timestamp).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
                {results.length === 0 && status?.status === 'Done' && (
                  <TableRow>
                    <TableCell colSpan={4} align="center">
                      Keine Ergebnisse gefunden.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )
      }
    </Container>
  )
}

export default RunDetailPage
