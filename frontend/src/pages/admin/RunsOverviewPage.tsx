// src/pages/admin/RunsOverviewPage.tsx
import React, { useEffect, useState, useMemo } from 'react'
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
  TableSortLabel,
  CircularProgress,
  Alert,
  TextField,
  MenuItem
} from '@mui/material'
import { useNavigate } from 'react-router-dom'
import type { RunListItem } from '../../api/models'
import { getRuns } from '../../api/api'

const fmt = (n?: number) => (typeof n === 'number' ? n.toFixed(2) : '—')

type OrderBy = 'created_at' | 'product_score_avg'

const DEFAULT_PAGE_SIZE = 20

const RunsOverviewPage: React.FC = () => {
  const [runs, setRuns] = useState<RunListItem[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  // Sortierung (clientseitig auf der aktuellen Seite)
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [orderBy, setOrderBy] = useState<OrderBy>('created_at')

  // Pagination (serverseitig per offset/limit)
  const [page, setPage] = useState<number>(0)
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE)

  // Merker, ob wir am Ende sind (runs.length < pageSize)
  const endOfList = runs.length < pageSize

  const handleRequestSort = (property: OrderBy) => {
    const isAsc = orderBy === property && order === 'asc'
    setOrder(isAsc ? 'desc' : 'asc')
    setOrderBy(property)
  }

  const sortedRuns = useMemo(() => {
    return [...runs].sort((a, b) => {
      let comp = 0
      if (orderBy === 'created_at') {
        const da = new Date(a.created_at).getTime()
        const db = new Date(b.created_at).getTime()
        comp = da - db
      } else {
        // PQS Ø (roher Produkt-Score Durchschnitt)
        const sa = a.metrics?.product_score_avg ?? -Infinity
        const sb = b.metrics?.product_score_avg ?? -Infinity
        comp = sa - sb
      }
      return order === 'asc' ? comp : -comp
    })
  }, [runs, order, orderBy])

  const navigate = useNavigate()

  const loadRuns = async (opts?: { keepPage?: boolean }) => {
    setLoading(true)
    setError(null)
    try {
      const offset = page * pageSize
      const limit = pageSize
      const data = await getRuns({ includeMetrics: true, offset, limit })
      setRuns(data)
      // Wenn wir z. B. auf „Weiter“ klicken, aber gar keine Daten mehr kommen (z. B. leere Seite),
      // springen wir eine Seite zurück (nur wenn nicht keepPage explizit gesetzt ist).
      if (!opts?.keepPage && data.length === 0 && page > 0) {
        setPage(p => Math.max(0, p - 1))
      }
    } catch (err: any) {
      console.error(err)
      setError(err.message || 'Fehler beim Laden der Runs')
    } finally {
      setLoading(false)
    }
  }

  // Initial + bei page/pageSize Änderungen neu laden
  useEffect(() => {
    loadRuns({ keepPage: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize])

  const handleRefresh = () => loadRuns({ keepPage: true })

  const handlePrev = () => {
    if (page > 0) setPage(p => p - 1)
  }
  const handleNext = () => {
    if (!endOfList) setPage(p => p + 1)
  }
  const handlePageSizeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextSize = Number(e.target.value) || DEFAULT_PAGE_SIZE
    setPage(0)            // bei Änderung der Größe zurück zur ersten Seite
    setPageSize(nextSize)
  }

  return (
    <Container sx={{ mt: 4, mb: 4 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h4">Übersicht aller Test Runs</Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            select
            size="small"
            label="Zeilen/Seite"
            value={pageSize}
            onChange={handlePageSizeChange}
            sx={{ width: 140 }}
          >
            {[10, 20, 50].map(sz => (
              <MenuItem key={sz} value={sz}>{sz}</MenuItem>
            ))}
          </TextField>
          <Button variant="outlined" onClick={handlePrev} disabled={loading || page === 0}>
            ← Zurück
          </Button>
          <Typography variant="body2" sx={{ mx: 1, minWidth: 72, textAlign: 'center' }}>
            Seite {page + 1}
          </Typography>
          <Button variant="outlined" onClick={handleNext} disabled={loading || endOfList}>
            Weiter →
          </Button>
          <Button variant="outlined" onClick={handleRefresh} disabled={loading}>
            {loading ? <CircularProgress size={20} /> : 'Aktualisieren'}
          </Button>
        </Stack>
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
                <TableCell sortDirection={orderBy === 'created_at' ? order : false}>
                  <TableSortLabel
                    active={orderBy === 'created_at'}
                    direction={orderBy === 'created_at' ? order : 'asc'}
                    onClick={() => handleRequestSort('created_at')}
                  >
                    Erstellt am
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right" sortDirection={orderBy === 'product_score_avg' ? order : false}>
                  <TableSortLabel
                    active={orderBy === 'product_score_avg'}
                    direction={orderBy === 'product_score_avg' ? order : 'asc'}
                    onClick={() => handleRequestSort('product_score_avg')}
                  >
                    PQS Ø
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right">Prompts</TableCell>
                <TableCell align="right">Fertig</TableCell>
                <TableCell align="right">Aktion</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sortedRuns.map((run) => (
                <TableRow key={run.id} hover>
                  <TableCell>{run.id}</TableCell>
                  <TableCell>{run.status}</TableCell>
                  <TableCell>{new Date(run.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right">{fmt(run.metrics?.product_score_avg)}</TableCell>
                  <TableCell align="right">{run.prompt_ids.length}</TableCell>
                  <TableCell align="right">
                    {run.status === 'Done' ? run.prompt_ids.length : '—'}
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
              {sortedRuns.length === 0 && !loading && (
                <TableRow>
                  <TableCell colSpan={7} align="center">
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
