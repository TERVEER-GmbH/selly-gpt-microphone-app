// src/pages/admin/RunsOverviewPage.tsx
import React, { useEffect, useMemo, useState } from 'react'
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
  MenuItem,
  IconButton,
  Tooltip,
  Chip,
  LinearProgress,
  ToggleButton,
  ToggleButtonGroup,
  Autocomplete,
  Skeleton,
  Menu,
  ListItemIcon,
  ListItemText,
} from '@mui/material'
import MoreVertIcon from '@mui/icons-material/MoreVert'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import FileDownloadIcon from '@mui/icons-material/FileDownload'
import LooksOneIcon from '@mui/icons-material/LooksOne'
import LooksTwoIcon from '@mui/icons-material/LooksTwo'
import DriveFileRenameOutlineIcon from '@mui/icons-material/DriveFileRenameOutline'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
import type { RunListItem } from '../../api/models'
import { getRuns, renameRun } from '../../api/api'
import RenameRunDialog from '../../components/admin/RenameRunDialog'

const fmt2 = (n?: number) => (typeof n === 'number' && Number.isFinite(n) ? n.toFixed(2) : '—')
const fmt0 = (n?: number) => (typeof n === 'number' && Number.isFinite(n) ? Math.round(n).toString() : '—')

type OrderBy = 'created_at' | 'product_score_avg'
type StatusTab = 'All' | 'Pending' | 'Running' | 'Done'

const DEFAULT_PAGE_SIZE = 20

const StatusChip: React.FC<{ s: RunListItem['status'] }> = ({ s }) => (
  <Chip
    size="small"
    label={s}
    color={s === 'Done' ? 'success' : s === 'Running' ? 'info' : 'default'}
    variant={s === 'Pending' ? 'outlined' : 'filled'}
  />
)

const RelativeTime: React.FC<{ iso: string }> = ({ iso }) => {
  const d = new Date(iso)
  const abs = d.toLocaleString()
  const ms = d.getTime() - Date.now()
  const min = Math.round(ms / 60000)
  const hr = Math.round(min / 60)
  const day = Math.round(hr / 24)
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  let text = abs
  if (Math.abs(min) < 60) text = rtf.format(min, 'minute')
  else if (Math.abs(hr) < 48) text = rtf.format(hr, 'hour')
  else text = rtf.format(day, 'day')
  return <Tooltip title={abs}><span>{text}</span></Tooltip>
}

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

  // Filter
  const [q, setQ] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusTab>('All')
  const [modelFilter, setModelFilter] = useState<string | null>(null)
  const [minPqs, setMinPqs] = useState<number>(0)

  // Rename Dialog
  const [renameOpen, setRenameOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [selectedRun, setSelectedRun] = useState<RunListItem | null>(null)

  // Row actions menu
  const [actionAnchor, setActionAnchor] = useState<null | HTMLElement>(null)
  const [actionRun, setActionRun] = useState<RunListItem | null>(null)

  const endOfList = runs.length < pageSize
  const navigate = useNavigate()

  const handleRequestSort = (property: OrderBy) => {
    const isAsc = orderBy === property && order === 'asc'
    setOrder(isAsc ? 'desc' : 'asc')
    setOrderBy(property)
  }

  const loadRuns = async () => {
    setLoading(true)
    setError(null)
    try {
      const offset = page * pageSize
      const limit = pageSize
      const data = await getRuns({ includeMetrics: true, offset, limit })
      if (data.length === 0 && page > 0) {
        // Leere Seite -> eine Seite zurückspringen und neu laden
        setPage(p => Math.max(0, p - 1))
      } else {
        setRuns(data)
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
    loadRuns()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize])

  const handleRefresh = () => loadRuns()
  const handlePrev = () => { if (page > 0) setPage(p => p - 1) }
  const handleNext = () => { if (!endOfList) setPage(p => p + 1) }
  const handlePageSizeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextSize = Number(e.target.value) || DEFAULT_PAGE_SIZE
    setPage(0)
    setPageSize(nextSize)
  }

  const modelOptions = useMemo(
    () => Array.from(new Set(runs.map(r => r.params?.model).filter(Boolean))) as string[],
    [runs]
  )

  // Filter -> gefilterte Liste (nur für aktuelle Seite)
  const filteredRuns = useMemo(() => {
    const ql = q.trim().toLowerCase()
    return runs.filter(r => {
      const name = (r.name || '').toLowerCase()
      const id = r.id.toLowerCase()
      const matchesQ = !ql || name.includes(ql) || id.includes(ql)
      const matchesStatus = statusFilter === 'All' || r.status === statusFilter
      const matchesModel = !modelFilter || r.params?.model === modelFilter
      const pqs = r.metrics?.product_score_avg ?? 0
      const matchesPqs = pqs >= minPqs
      return matchesQ && matchesStatus && matchesModel && matchesPqs
    })
  }, [runs, q, statusFilter, modelFilter, minPqs])

  // Sortierung der gefilterten Liste
  const sortedRuns = useMemo(() => {
    const arr = [...filteredRuns]
    arr.sort((a, b) => {
      if (orderBy === 'created_at') {
        const da = new Date(a.created_at).getTime()
        const db = new Date(b.created_at).getTime()
        return (order === 'asc' ? 1 : -1) * (da - db)
      } else {
        const sa = a.metrics?.product_score_avg ?? -Infinity
        const sb = b.metrics?.product_score_avg ?? -Infinity
        return (order === 'asc' ? 1 : -1) * (sa - sb)
      }
    })
    return arr
  }, [filteredRuns, order, orderBy])

  // KPIs für aktuelle gefilterte Seite
  const avgPqsFiltered = filteredRuns.length
    ? filteredRuns.reduce((s, r) => s + (r.metrics?.product_score_avg ?? 0), 0) / filteredRuns.length
    : 0
  const doneCount = filteredRuns.filter(r => r.status === 'Done').length

  // Rename
  const openRename = (run: RunListItem) => {
    setSelectedRun(run)
    setRenameOpen(true)
  }
  const closeRename = () => {
    setRenameOpen(false)
    setSelectedRun(null)
  }
  const saveRename = async (newName: string) => {
    if (!selectedRun) return
    try {
      setRenaming(true)
      await renameRun(selectedRun.id, newName)
      setRuns(prev => prev.map(r => (r.id === selectedRun.id ? { ...r, name: newName } : r)))
      closeRename()
    } catch (e) {
      console.error(e)
      alert('Umbenennen fehlgeschlagen.')
    } finally {
      setRenaming(false)
    }
  }

  // Row actions
  const openActions = (e: React.MouseEvent<HTMLElement>, run: RunListItem) => {
    setActionAnchor(e.currentTarget)
    setActionRun(run)
  }
  const closeActions = () => {
    setActionAnchor(null)
    setActionRun(null)
  }

  return (
    <Container sx={{ mt: 4, mb: 4 }}>
      {/* Header mit Pagination-Controls */}
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

      {/* KPI-Bar */}
      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
          <Stack direction="row" spacing={1} flex={1} useFlexGap>
            <Chip size="small" label={`Runs: ${filteredRuns.length}`} />
            <Chip size="small" label={`PQS Ø: ${fmt0(avgPqsFiltered)}`} color="primary" />
            <Chip size="small" label={`Done: ${doneCount}/${filteredRuns.length || 0}`} />
          </Stack>
        </Stack>
      </Paper>

      {/* Filterbar */}
      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="center">
          <TextField
            size="small"
            label="Suchen (Name/ID)"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            sx={{ minWidth: 240 }}
          />

          <ToggleButtonGroup
            size="small"
            exclusive
            value={statusFilter}
            onChange={(_, v: StatusTab | null) => v && setStatusFilter(v)}
          >
            {(['All', 'Pending', 'Running', 'Done'] as StatusTab[]).map(s => (
              <ToggleButton key={s} value={s}>{s}</ToggleButton>
            ))}
          </ToggleButtonGroup>

          <Autocomplete<string>
            options={modelOptions}
            value={modelFilter}
            onChange={(_, v) => setModelFilter(v)}
            renderInput={(params) => <TextField {...params} label="Modell" size="small" />}
            sx={{ minWidth: 200 }}
            clearOnEscape
          />

          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body2" color="text.secondary">Min PQS:</Typography>
            <TextField
              size="small"
              type="number"
              inputProps={{ min: 0, step: 1 }}
              value={minPqs}
              onChange={(e) => setMinPqs(Number(e.target.value) || 0)}
              sx={{ width: 90 }}
            />
          </Stack>
        </Stack>
      </Paper>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Tabelle */}
      <TableContainer component={Paper}>
        <Table size="small" stickyHeader
          sx={{
            '& thead th': { position: 'sticky', top: 0, zIndex: 1, bgcolor: 'background.paper' },
            '& tbody tr:nth-of-type(odd)': { bgcolor: 'action.hover' },
            '& tbody tr .renameBtn': { opacity: 0, transition: 'opacity .15s' },
            '& tbody tr:hover .renameBtn': { opacity: 1 },
          }}
        >
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Run ID</TableCell>
              <TableCell>Status</TableCell>
              <TableCell sortDirection={orderBy === 'created_at' ? order : false}>
                <TableSortLabel
                  active={orderBy === 'created_at'}
                  direction={orderBy === 'created_at' ? order : 'asc'}
                  onClick={() => handleRequestSort('created_at')}
                >
                  Erstellt
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
              <TableCell align="right">Aktionen</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {/* Loading Skeletons */}
            {loading && !runs.length && Array.from({ length: 8 }).map((_, i) => (
              <TableRow key={`sk-${i}`}>
                <TableCell><Skeleton width={220} /></TableCell>
                <TableCell><Skeleton width={160} /></TableCell>
                <TableCell><Skeleton width={100} /></TableCell>
                <TableCell><Skeleton width={140} /></TableCell>
                <TableCell align="right"><Skeleton width={60} /></TableCell>
                <TableCell align="right"><Skeleton width={60} /></TableCell>
                <TableCell align="right"><Skeleton width={120} /></TableCell>
                <TableCell align="right"><Skeleton width={100} /></TableCell>
              </TableRow>
            ))}

            {!loading && sortedRuns.map((run) => (
              <TableRow
                key={run.id}
                hover
                sx={run.status === 'Running' ? { borderLeft: 3, borderLeftColor: 'info.main' } : undefined}
              >
                {/* Name + inline rename */}
                <TableCell sx={{ maxWidth: 400 }}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2" noWrap title={run.name || ''}>
                      {run.name || '—'}
                    </Typography>
                    <Tooltip title="Namen ändern">
                      <IconButton size="small" className="renameBtn" onClick={() => openRename(run)}>
                        <DriveFileRenameOutlineIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </TableCell>

                {/* ID monospace */}
                <TableCell sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', userSelect: 'text' }}>
                  {run.id}
                </TableCell>

                {/* Status + zarter Progress wenn nicht Done */}
                <TableCell>
                  <Stack spacing={0.5}>
                    <StatusChip s={run.status} />
                    {run.status !== 'Done' && (
                      <LinearProgress variant="indeterminate" sx={{ height: 3, borderRadius: 999 }} />
                    )}
                  </Stack>
                </TableCell>

                {/* Relative Zeit */}
                <TableCell>
                  <RelativeTime iso={run.created_at} />
                </TableCell>

                {/* PQS Ø rechtsbündig */}
                <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                  {fmt0(run.metrics?.product_score_avg)}
                </TableCell>

                {/* Prompt counts */}
                <TableCell align="right">{run.prompt_ids.length}</TableCell>
                <TableCell align="right">
                  {run.status === 'Done' ? run.prompt_ids.length : '—'}
                </TableCell>

                {/* Actions Menu */}
                <TableCell align="right">
                  <IconButton onClick={(e) => openActions(e, run)}>
                    <MoreVertIcon />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}

            {!loading && sortedRuns.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} align="center">
                  Keine Runs gefunden.{" "}
                  <Button size="small" onClick={() => { setQ(''); setStatusFilter('All'); setModelFilter(null); setMinPqs(0); }}>
                    Filter zurücksetzen
                  </Button>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Row actions menu */}
      <Menu
        anchorEl={actionAnchor}
        open={Boolean(actionAnchor)}
        onClose={closeActions}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <MenuItem onClick={() => { if (actionRun) navigate(`/admin/runs/${actionRun.id}`); closeActions() }}>
          <ListItemIcon><OpenInNewIcon fontSize="small" /></ListItemIcon>
          <ListItemText>Details</ListItemText>
        </MenuItem>
        <MenuItem component="a" href={actionRun ? `/admin/runs/${actionRun.id}/export?fmt=csv` : '#'} onClick={closeActions}>
          <ListItemIcon><FileDownloadIcon fontSize="small" /></ListItemIcon>
          <ListItemText>Export CSV</ListItemText>
        </MenuItem>
        <MenuItem component={RouterLink} to={actionRun ? `/admin/compare?left=${actionRun.id}` : '#'} onClick={closeActions}>
          <ListItemIcon><LooksOneIcon fontSize="small" /></ListItemIcon>
          <ListItemText>Als A vergleichen</ListItemText>
        </MenuItem>
        <MenuItem component={RouterLink} to={actionRun ? `/admin/compare?right=${actionRun.id}` : '#'} onClick={closeActions}>
          <ListItemIcon><LooksTwoIcon fontSize="small" /></ListItemIcon>
          <ListItemText>Als B vergleichen</ListItemText>
        </MenuItem>
      </Menu>

      {/* Rename Dialog */}
      <RenameRunDialog
        open={renameOpen}
        initialName={selectedRun?.name || ''}
        onCancel={closeRename}
        onSave={saveRename}
        saving={renaming}
      />
    </Container>
  )
}

export default RunsOverviewPage
