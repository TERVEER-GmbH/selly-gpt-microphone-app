// src/pages/admin/RunDetailPage.tsx
import React from 'react'
import { useParams, Link as RouterLink } from 'react-router-dom'
import {
  Box,
  Button,
  Chip,
  Container,
  LinearProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
  IconButton,
  Divider,
  Alert,
  Collapse,
} from '@mui/material'
import type { ChipProps } from '@mui/material'
import Grid from '@mui/material/Grid'
import EditIcon from '@mui/icons-material/Edit'
import RefreshIcon from '@mui/icons-material/Refresh'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown'
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp'

import { getRunStatus, getRunResults, patchRunResult } from '../../api/api'
import type { RunStatus, TestResult, TestResultUpdate } from '../../api/models'
import ResultEditDialog from '../../components/ResultEditDialog/ResultEditDialog'

/* ===== Helpers ===== */

function fmt(n: number | undefined): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(2) : '—'
}

function subscore(r: TestResult): number {
  const x = r as unknown as Record<string, any>
  const vals = [
    Number.isFinite(x.relevance) ? x.relevance : 0,
    Number.isFinite(x.factual_accuracy) ? x.factual_accuracy : 0,
    Number.isFinite(x.completeness) ? x.completeness : 0,
    Number.isFinite(x.tone) ? x.tone : 0,
    Number.isFinite(x.comprehensibility) ? x.comprehensibility : 0,
  ]
  const sum = vals.reduce((a, b) => a + b, 0)
  return vals.length ? sum / vals.length : 0
}

function scoreColor(n: number): ChipProps['color'] {
  if (!Number.isFinite(n)) return 'default'
  if (n >= 4.5) return 'success'
  if (n >= 3.5) return 'info'
  if (n >= 2.5) return 'warning'
  return 'error'
}

function shortGolden(text: string, max = 120): string {
  if (!text) return ''
  const t = text.trim()
  if (t.length <= max) return t
  const cut = t.slice(0, max).replace(/\s+\S*$/, '')
  return `${cut}…`
}

function ClampText({
  text,
  lines = 2,
  title,
}: {
  text: string
  lines?: number
  title?: string
}) {
  return (
    <Tooltip title={title ?? text}>
      <Typography
        variant="body2"
        sx={{
          display: '-webkit-box',
          WebkitBoxOrient: 'vertical',
          WebkitLineClamp: lines,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'normal',
        }}
      >
        {text}
      </Typography>
    </Tooltip>
  )
}

const POLL_MS = 1200

/* ===== Row-Komponente (kompakt + aufklappbar) ===== */

function ResultRow({
  r,
  onEdit,
}: {
  r: TestResult
  onEdit: (r: TestResult) => void
}) {
  const [open, setOpen] = React.useState(false)

  const rel  = (r as any).relevance
  const fact = (r as any).factual_accuracy
  const comp = (r as any).completeness
  const tone = (r as any).tone
  const compr= (r as any).comprehensibility
  const avg  = subscore(r)

  return (
    <React.Fragment key={r.id}>
      <TableRow hover>
        <TableCell padding="checkbox" sx={{ width: 40 }}>
          <IconButton size="small" onClick={() => setOpen(s => !s)}>
            {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
          </IconButton>
        </TableCell>

        <TableCell sx={{ maxWidth: 520 }}>
          <Box sx={{ mb: 0.5 }}>
            <ClampText text={r.prompt_text} lines={2} />
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            Golden: {shortGolden(r.golden_answer, 140)}
          </Typography>
        </TableCell>

        <TableCell sx={{ maxWidth: 560 }}>
          <ClampText text={r.ai_response} lines={2} />
        </TableCell>

        <TableCell align="center">
          <Chip size="small" label={fmt(rel)} color={scoreColor(rel ?? 0)} />
        </TableCell>
        <TableCell align="center">
          <Chip size="small" label={fmt(fact)} color={scoreColor(fact ?? 0)} />
        </TableCell>
        <TableCell align="center">
          <Chip size="small" label={fmt(comp)} color={scoreColor(comp ?? 0)} />
        </TableCell>
        <TableCell align="center">
          <Chip size="small" label={fmt(tone)} color={scoreColor(tone ?? 0)} />
        </TableCell>
        <TableCell align="center">
          <Chip size="small" label={fmt(compr)} color={scoreColor(compr ?? 0)} />
        </TableCell>
        <TableCell align="center">
          <Chip size="small" label={fmt(avg)} color={scoreColor(avg)} />
        </TableCell>

        <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
          <IconButton color="primary" onClick={() => onEdit(r)}>
            <EditIcon />
          </IconButton>
        </TableCell>
      </TableRow>

      <TableRow>
        <TableCell colSpan={10} sx={{ p: 0, border: 0 }}>
          <Collapse in={open} timeout="auto" unmountOnExit>
            <Box
              sx={{
                p: 2,
                bgcolor: (t) => t.palette.action.hover, // <<— dezenter Grauton
                borderTop: '1px solid',
                borderColor: 'divider',
                borderRadius: 1,
              }}
            >
              <Grid container spacing={2} sx={{ width: '100%' }}>
                <Grid size={{ xs: 12 }}>
                  <Typography variant="subtitle2">Prompt</Typography>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                    {r.prompt_text}
                  </Typography>
                </Grid>

                <Grid size={{ xs: 12 }}>
                  <Typography variant="subtitle2">Golden Answer</Typography>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                    {r.golden_answer}
                  </Typography>
                </Grid>

                <Grid size={{ xs: 12 }}>
                  <Typography variant="subtitle2">AI-Antwort</Typography>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                    {r.ai_response}
                  </Typography>
                </Grid>

                <Grid size={{ xs: 12 }}>
                  <Divider sx={{ my: 1 }} />
                </Grid>

                {Boolean((r as any).relevance_comment) && (
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <Typography variant="caption" color="text.secondary">
                      Relevanz – Kommentar
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                      {(r as any).relevance_comment}
                    </Typography>
                  </Grid>
                )}
                {Boolean((r as any).factual_accuracy_comment) && (
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <Typography variant="caption" color="text.secondary">
                      Faktentreue – Kommentar
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                      {(r as any).factual_accuracy_comment}
                    </Typography>
                  </Grid>
                )}
                {Boolean((r as any).completeness_comment) && (
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <Typography variant="caption" color="text.secondary">
                      Vollständigkeit – Kommentar
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                      {(r as any).completeness_comment}
                    </Typography>
                  </Grid>
                )}
                {Boolean((r as any).tone_comment) && (
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <Typography variant="caption" color="text.secondary">
                      Tonalität – Kommentar
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                      {(r as any).tone_comment}
                    </Typography>
                  </Grid>
                )}
                {Boolean((r as any).comprehensibility_comment) && (
                  <Grid size={{ xs: 12 }}>
                    <Typography variant="caption" color="text.secondary">
                      Verständlichkeit – Kommentar
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                      {(r as any).comprehensibility_comment}
                    </Typography>
                  </Grid>
                )}
                {Boolean((r as any).overall_comment) && (
                  <Grid size={{ xs: 12 }}>
                    <Divider sx={{ my: 1 }} />
                    <Typography variant="caption" color="text.secondary">
                      Gesamt-Kommentar
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                      {(r as any).overall_comment}
                    </Typography>
                  </Grid>
                )}
              </Grid>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </React.Fragment>
  )
}

/* ===== Seite ===== */

const RunDetailPage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>()
  const [status, setStatus] = React.useState<RunStatus | null>(null)
  const [results, setResults] = React.useState<TestResult[]>([])
  const [loading, setLoading] = React.useState<boolean>(true)
  const [error, setError] = React.useState<string | null>(null)

  const [editing, setEditing] = React.useState<TestResult | null>(null)
  const [saving, setSaving] = React.useState<boolean>(false)

  const loadAll = React.useCallback(async () => {
    if (!runId) return
    setError(null)
    try {
      const [st, res] = await Promise.all([getRunStatus(runId), getRunResults(runId)])
      setStatus(st)
      setResults(res)
    } catch (e: any) {
      console.error(e)
      setError('Konnte Run/Ergebnisse nicht laden.')
    } finally {
      setLoading(false)
    }
  }, [runId])

  React.useEffect(() => {
    loadAll()
  }, [loadAll])

  React.useEffect(() => {
    if (!runId) return
    if (!status || status.status === 'Done') return
    if (editing) return

    const iv = window.setInterval(async () => {
      try {
        const st = await getRunStatus(runId)
        setStatus(st)
        const res = await getRunResults(runId)
        setResults(res)
      } catch {
        /* ignore */
      }
    }, POLL_MS)

    return () => window.clearInterval(iv)
  }, [runId, status?.status, editing])

  const handleRefresh = async () => {
    await loadAll()
  }

  const handleOpenEdit = (r: TestResult) => setEditing(r)
  const handleCloseEdit = () => setEditing(null)

  const handleSaveEdit = async (patch: TestResultUpdate) => {
    if (!runId || !editing) return
    try {
      setSaving(true)
      await patchRunResult(runId, editing.id, patch)
      setResults(prev => prev.map(r => (r.id === editing.id ? ({ ...r, ...patch } as TestResult) : r)))
      setEditing(null)
    } catch (e: any) {
      console.error(e)
      alert('Speichern fehlgeschlagen.')
    } finally {
      setSaving(false)
    }
  }

  const progress =
    status ? Math.min(100, Math.round((status.completed / Math.max(1, status.total)) * 100)) : 0

  return (
    <Container sx={{ py: 3 }}>
      <Stack direction="row" alignItems="center" spacing={1} mb={2}>
        <Button component={RouterLink} to="/admin/runs" startIcon={<ArrowBackIcon />}>
          Zurück zur Übersicht
        </Button>
        <Box sx={{ flexGrow: 1 }} />
        <Button onClick={handleRefresh} startIcon={<RefreshIcon />} variant="outlined">
          Aktualisieren
        </Button>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} sx={{ width: '100%' }}>
          <Grid size={{ xs: 12 }}>
            <Typography variant="h6">Run {status?.run_id ?? runId}</Typography>
          </Grid>

          <Grid size={{ xs: 12, sm: 6 }}>
            <Typography variant="body2" color="text.secondary">
              Modell / Temperatur / Max Tokens
            </Typography>
            <Typography variant="body1">
              {status?.params?.model ?? '—'} • {status?.params?.temperature ?? '—'} •{' '}
              {status?.params?.max_tokens ?? '—'}
            </Typography>
          </Grid>

          <Grid size={{ xs: 12, sm: 6 }}>
            <Typography variant="body2" color="text.secondary">
              Erstellt am
            </Typography>
            <Typography variant="body1">
              {status?.created_at ? new Date(status.created_at).toLocaleString() : '—'}
            </Typography>
          </Grid>

          <Grid size={{ xs: 12, sm: 6 }}>
            <Typography variant="body2" color="text.secondary">
              Status
            </Typography>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Chip
                label={status?.status ?? '—'}
                color={
                  status?.status === 'Done'
                    ? 'success'
                    : status?.status === 'Running'
                    ? 'info'
                    : 'default'
                }
                size="small"
              />
              <Typography variant="body2">
                {status?.completed ?? 0} / {status?.total ?? 0}
              </Typography>
            </Stack>
            {status && status.status !== 'Done' && (
              <Box sx={{ mt: 1 }}>
                <LinearProgress variant="determinate" value={progress} />
              </Box>
            )}
          </Grid>

          <Grid size={{ xs: 12, sm: 6 }}>
            <Typography variant="body2" color="text.secondary">
              Aggregierter Subscore (Ø der fünf Kategorien)
            </Typography>
            <Typography variant="h6">
              {results.length ? fmt(results.reduce((a, r) => a + subscore(r), 0) / results.length) : '—'}
            </Typography>
          </Grid>
        </Grid>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Ergebnisse ({results.length})
        </Typography>
        <Divider sx={{ mb: 2 }} />

        <TableContainer>
          <Table size="small" aria-label="results table">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 40 }} />
                <TableCell sx={{ minWidth: 360 }}>Prompt</TableCell>
                <TableCell sx={{ minWidth: 420 }}>AI-Antwort</TableCell>
                <TableCell align="center">Rel.</TableCell>
                <TableCell align="center">Fact</TableCell>
                <TableCell align="center">Comp.</TableCell>
                <TableCell align="center">Tone</TableCell>
                <TableCell align="center">Compr.</TableCell>
                <TableCell align="center">Ø</TableCell>
                <TableCell align="right">Aktion</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {results.map((r) => (
                <ResultRow key={r.id} r={r} onEdit={setEditing} />
              ))}
              {(!results || results.length === 0) && !loading && (
                <TableRow>
                  <TableCell colSpan={10} align="center">
                    <Typography variant="body2" color="text.secondary">
                      Noch keine Ergebnisse vorhanden.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      {editing && (
        <ResultEditDialog
          key={editing.id}
          open={!!editing}
          initial={editing}
          onClose={handleCloseEdit}
          onSave={handleSaveEdit}
          saving={saving}
        />
      )}
    </Container>
  )
}

export default RunDetailPage
