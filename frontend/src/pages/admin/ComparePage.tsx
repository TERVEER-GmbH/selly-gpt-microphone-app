// src/pages/admin/ComparePage.tsx
import React from 'react'
import { useSearchParams, Link as RouterLink } from 'react-router-dom'
import {
  Container, Stack, Paper, Typography, Chip, Button, Alert,
  Table, TableHead, TableRow, TableCell, TableBody, TableContainer,
  Tooltip, Box, ToggleButtonGroup, ToggleButton, TableSortLabel, Divider,
  Autocomplete, TextField, IconButton
} from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import DownloadIcon from '@mui/icons-material/Download'
import SwapHorizIcon from '@mui/icons-material/SwapHoriz'
import type { CompareFull, ComparePair, RunListItem } from '../../api/models'
import { compareRuns, exportCompare, getRuns } from '../../api/api'

const fmt = (n?: number) => (typeof n === 'number' ? n.toFixed(2) : '—')
const truncate = (s: string, len = 120) => (s && s.length > len ? s.slice(0, len - 1) + '…' : s)

type RowFilter = 'all' | 'matched' | 'left_only' | 'right_only'
type SortKey = 'delta_pqs' | 'pqs_left' | 'pqs_right'

const typeLabel = (p: ComparePair) =>
  p.matched ? 'matched' : p.side === 'left_only' ? 'left_only' : 'right_only'

const rowBg = (p: ComparePair) => (p.matched ? 'transparent' : '#f6f6f7')

// PQS-Ø aus pairs berechnen (roh)
function avgPqsFromPairs(pairs: ComparePair[], side: 'left'|'right'): number | undefined {
  const vals: number[] = []
  for (const p of pairs) {
    if (side === 'left') {
      if (p.matched) vals.push(p.left.product_score_raw)
      else if (p.side === 'left_only') vals.push(p.left.product_score_raw)
    } else {
      if (p.matched) vals.push(p.right.product_score_raw)
      else if (p.side === 'right_only') vals.push(p.right.product_score_raw)
    }
  }
  if (!vals.length) return undefined
  return vals.reduce((a, b) => a + b, 0) / vals.length
}

const ComparePage: React.FC = () => {
  const [sp, setSp] = useSearchParams()
  const left  = sp.get('left')  || ''
  const right = sp.get('right') || ''

  const [runs, setRuns] = React.useState<RunListItem[]>([])
  const [runsLoading, setRunsLoading] = React.useState<boolean>(false)
  const [runsError, setRunsError] = React.useState<string | null>(null)

  const [data, setData] = React.useState<CompareFull | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState<boolean>(false)

  const [filter, setFilter] = React.useState<RowFilter>('all')
  const [order, setOrder] = React.useState<'asc' | 'desc'>('desc')
  const [orderBy, setOrderBy] = React.useState<SortKey>('delta_pqs')

  React.useEffect(() => {
    const loadRuns = async () => {
      setRunsLoading(true)
      setRunsError(null)
      try {
        const rs = await getRuns({ includeMetrics: true })
        setRuns(rs)
      } catch (e: any) {
        console.error(e)
        setRunsError(e?.message || 'Runs konnten nicht geladen werden.')
      } finally {
        setRunsLoading(false)
      }
    }
    loadRuns()
  }, [])

  const load = React.useCallback(async () => {
    if (!left || !right) { setData(null); return }
    setError(null)
    setLoading(true)
    try {
      const res = await compareRuns(left, right, 'full') as CompareFull
      setData(res)
    } catch (e: any) {
      console.error(e)
      setError(e?.message || 'Vergleich konnte nicht geladen werden.')
    } finally {
      setLoading(false)
    }
  }, [left, right])

  React.useEffect(() => { load() }, [load])

  const setLeft = (id?: string | null) => {
    const next = new URLSearchParams(sp)
    if (id) next.set('left', id); else next.delete('left')
    setSp(next, { replace: true })
  }
  const setRight = (id?: string | null) => {
    const next = new URLSearchParams(sp)
    if (id) next.set('right', id); else next.delete('right')
    setSp(next, { replace: true })
  }
  const swapLR = () => {
    if (!left && !right) return
    const next = new URLSearchParams(sp)
    if (right) next.set('left', right); else next.delete('left')
    if (left)  next.set('right', left);  else next.delete('right')
    setSp(next, { replace: true })
  }

  const runA = runs.find(r => r.id === left) || null
  const runB = runs.find(r => r.id === right) || null

  const handleSort = (key: SortKey) => {
    const isAsc = orderBy === key && order === 'asc'
    setOrder(isAsc ? 'desc' : 'asc')
    setOrderBy(key)
  }

  const filtered = React.useMemo(() => {
    if (!data) return []
    let rows = data.pairs
    if (filter !== 'all') rows = rows.filter(p => (typeLabel(p) === filter))
    const getter = (p: ComparePair, k: SortKey) => {
      if (k === 'delta_pqs') {
        // matched -> delta; left_only groß positiv; right_only groß negativ (damit sortierbar)
        return p.matched ? (p.right.product_score_raw - p.left.product_score_raw)
             : (p.side === 'left_only' ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY)
      }
      if (k === 'pqs_left') {
        return p.matched ? p.left.product_score_raw
             : (p.side === 'left_only' ? p.left.product_score_raw : Number.NEGATIVE_INFINITY)
      }
      if (k === 'pqs_right') {
        return p.matched ? p.right.product_score_raw
             : (p.side === 'right_only' ? p.right.product_score_raw : Number.NEGATIVE_INFINITY)
      }
      return 0
    }
    const cmp = (a: ComparePair, b: ComparePair) => {
      const da = getter(a, orderBy)
      const db = getter(b, orderBy)
      return (da - db) * (order === 'asc' ? 1 : -1)
    }
    return [...rows].sort(cmp)
  }, [data, filter, order, orderBy])

  const pqsAvgLeft  = data ? avgPqsFromPairs(data.pairs, 'left')  : undefined
  const pqsAvgRight = data ? avgPqsFromPairs(data.pairs, 'right') : undefined
  const pqsDelta    = (pqsAvgLeft != null && pqsAvgRight != null) ? (pqsAvgRight - pqsAvgLeft) : undefined

  return (
    <Container sx={{ py: 3 }}>
      {/* Top-Bar */}
      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} alignItems={{ xs: 'stretch', lg: 'center' }} mb={2}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Button component={RouterLink} to="/admin/runs" startIcon={<ArrowBackIcon />}>
            Zurück zu Runs
          </Button>
        </Stack>

        <Box sx={{ flexGrow: 1 }} />

        {/* Run Selectors */}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ xs: 'stretch', sm: 'center' }}>
          <Autocomplete<RunListItem>
            sx={{ minWidth: 260 }}
            options={runs}
            loading={runsLoading}
            value={runA}
            onChange={(_, v) => setLeft(v?.id)}
            getOptionLabel={(opt) => opt ? `${opt.id} — ${new Date(opt.created_at).toLocaleString()} — PQS Ø: ${fmt(opt.metrics?.product_score_avg)}` : ''}
            isOptionEqualToValue={(o, v) => o.id === v.id}
            renderInput={(params) => <TextField {...params} label="Run A wählen" placeholder="Run suchen…" size="small" />}
          />
          <IconButton aria-label="A ↔ B tauschen" onClick={swapLR}><SwapHorizIcon /></IconButton>
          <Autocomplete<RunListItem>
            sx={{ minWidth: 260 }}
            options={runs}
            loading={runsLoading}
            value={runB}
            onChange={(_, v) => setRight(v?.id)}
            getOptionLabel={(opt) => opt ? `${opt.id} — ${new Date(opt.created_at).toLocaleString()} — PQS Ø: ${fmt(opt.metrics?.product_score_avg)}` : ''}
            isOptionEqualToValue={(o, v) => o.id === v.id}
            renderInput={(params) => <TextField {...params} label="Run B wählen" placeholder="Run suchen…" size="small" />}
          />
        </Stack>

        {/* Export */}
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => exportCompare(left, right, 'csv')} disabled={!left || !right}>
            Export CSV
          </Button>
          <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => exportCompare(left, right, 'json')} disabled={!left || !right}>
            Export JSON
          </Button>
        </Stack>
      </Stack>

      {runsError && <Alert severity="error" sx={{ mb: 2 }}>{runsError}</Alert>}
      {(!left || !right) && <Alert severity="warning" sx={{ mb: 2 }}>Bitte oben <strong>Run A</strong> und <strong>Run B</strong> auswählen.</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* KPI Header */}
      {data && (
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>Vergleich A/B</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
              <Typography variant="subtitle2" color="text.secondary">Run A</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>{data.summary.left.run_id}</Typography>
              <Stack direction="row" spacing={2}>
                <Chip label={`PQS Ø: ${fmt(pqsAvgLeft)}`} color="primary" />
                <Chip label={`Subscore Ø: ${fmt(data.summary.left.avg_subscore)}`} />
                <Chip label={`N: ${data.summary.left.count}`} />
              </Stack>
            </Paper>

            <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
              <Typography variant="subtitle2" color="text.secondary">Run B</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>{data.summary.right.run_id}</Typography>
              <Stack direction="row" spacing={2}>
                <Chip label={`PQS Ø: ${fmt(pqsAvgRight)}`} color="primary" />
                <Chip label={`Subscore Ø: ${fmt(data.summary.right.avg_subscore)}`} />
                <Chip label={`N: ${data.summary.right.count}`} />
              </Stack>
            </Paper>

            <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
              <Typography variant="subtitle2" color="text.secondary">Delta & Coverage</Typography>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', sm: 'repeat(3, max-content)' },
                  columnGap: 1.5,
                  rowGap: 1,
                  alignItems: 'center',
                  justifyItems: 'start',
                  mt: 0.5,
                }}
              >
                <Chip size="small" label={`Δ PQS Ø: ${fmt(pqsDelta)}`} color="secondary" />
                <Chip size="small" label={`Intersection: ${data.summary.coverage.intersection}`} />
                <Chip size="small" label={`Union: ${data.summary.coverage.union}`} />
                <Chip size="small" label={`Left only: ${data.summary.coverage.left_only}`} />
                <Chip size="small" label={`Right only: ${data.summary.coverage.right_only}`} />
              </Box>
            </Paper>
          </Stack>
        </Paper>
      )}

      {/* Filter + Sort */}
      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="center" justifyContent="space-between">
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body2" color="text.secondary">Zeige:</Typography>
            <ToggleButtonGroup size="small" exclusive value={filter} onChange={(_, v: RowFilter | null) => v && setFilter(v)}>
              <ToggleButton value="all">Alle</ToggleButton>
              <ToggleButton value="matched">Matched</ToggleButton>
              <ToggleButton value="left_only">Nur A</ToggleButton>
              <ToggleButton value="right_only">Nur B</ToggleButton>
            </ToggleButtonGroup>
          </Stack>

          <Stack direction="row" spacing={2} alignItems="center">
            <Typography variant="body2" color="text.secondary">Sortieren nach:</Typography>
            <TableSortLabel
              active={orderBy === 'delta_pqs'}
              direction={orderBy === 'delta_pqs' ? order : 'desc'}
              onClick={() => handleSort('delta_pqs')}
            >
              Δ PQS
            </TableSortLabel>
            <TableSortLabel
              active={orderBy === 'pqs_left'}
              direction={orderBy === 'pqs_left' ? order : 'desc'}
              onClick={() => handleSort('pqs_left')}
            >
              PQS A
            </TableSortLabel>
            <TableSortLabel
              active={orderBy === 'pqs_right'}
              direction={orderBy === 'pqs_right' ? order : 'desc'}
              onClick={() => handleSort('pqs_right')}
            >
              PQS B
            </TableSortLabel>
          </Stack>
        </Stack>
      </Paper>

      {/* Tabelle */}
      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Typ</TableCell>
              <TableCell>Prompt</TableCell>
              <TableCell>AI A</TableCell>
              <TableCell>AI B</TableCell>
              <TableCell align="right">PQS A</TableCell>
              <TableCell align="right">PQS B</TableCell>
              <TableCell align="right">Δ PQS</TableCell>
              <TableCell align="right">Ø A</TableCell>
              <TableCell align="right">Ø B</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading && <TableRow><TableCell colSpan={9}>Lade…</TableCell></TableRow>}
            {!loading && data && filtered.map((p) => {
              const typ = typeLabel(p)
              const pqsA = p.matched ? p.left.product_score_raw : (p.side === 'left_only' ? p.left.product_score_raw : undefined)
              const pqsB = p.matched ? p.right.product_score_raw : (p.side === 'right_only' ? p.right.product_score_raw : undefined)
              const subA  = p.matched ? p.left.subscore : (p.side === 'left_only' ? p.left.subscore : undefined)
              const subB  = p.matched ? p.right.subscore : (p.side === 'right_only' ? p.right.subscore : undefined)
              const delta = (pqsA != null && pqsB != null) ? (pqsB - pqsA) : undefined

              const promptText = p.matched ? p.left.prompt_text : (p.side === 'left_only' ? p.left.prompt_text : p.right.prompt_text)
              const aiA = p.matched ? p.left.ai_response : (p.side === 'left_only' ? p.left.ai_response : '')
              const aiB = p.matched ? p.right.ai_response : (p.side === 'right_only' ? p.right.ai_response : '')

              return (
                <TableRow key={p.prompt_key} sx={{ backgroundColor: rowBg(p) }}>
                  <TableCell>
                    {typ === 'matched' ? (
                      <Chip size="small" label="Matched" color="success" />
                    ) : typ === 'left_only' ? (
                      <Chip size="small" label="Nur A" color="default" />
                    ) : (
                      <Chip size="small" label="Nur B" color="default" />
                    )}
                  </TableCell>

                  <TableCell sx={{ maxWidth: 320 }}>
                    <Tooltip title={promptText}><span>{truncate(promptText, 140)}</span></Tooltip>
                  </TableCell>

                  <TableCell sx={{ maxWidth: 360 }}>
                    {aiA ? <Tooltip title={aiA}><span>{truncate(aiA, 160)}</span></Tooltip> : <Typography variant="body2" color="text.disabled">—</Typography>}
                  </TableCell>

                  <TableCell sx={{ maxWidth: 360 }}>
                    {aiB ? <Tooltip title={aiB}><span>{truncate(aiB, 160)}</span></Tooltip> : <Typography variant="body2" color="text.disabled">—</Typography>}
                  </TableCell>

                  <TableCell align="right">{fmt(pqsA)}</TableCell>
                  <TableCell align="right">{fmt(pqsB)}</TableCell>
                  <TableCell align="right">{fmt(delta)}</TableCell>
                  <TableCell align="right">{fmt(subA)}</TableCell>
                  <TableCell align="right">{fmt(subB)}</TableCell>
                </TableRow>
              )
            })}
            {!loading && data && filtered.length === 0 && (
              <TableRow><TableCell colSpan={9} align="center">Keine Einträge für den Filter.</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Box mt={2}>
        <Divider sx={{ mb: 1 }} />
        <Typography variant="caption" color="text.secondary">
          * PQS = Produkt der fünf Kategorien (Skala 1–5) → Bereich 1…3125.
        </Typography>
      </Box>
    </Container>
  )
}

export default ComparePage
