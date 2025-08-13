// src/components/run-detail/ResultsTable.tsx
import React from 'react'
import {
  Box, Chip, Collapse, Divider, IconButton, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Tooltip, Typography
} from '@mui/material'
import EditIcon from '@mui/icons-material/Edit'
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown'
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp'
import type { ChipProps } from '@mui/material'
import Grid from '@mui/material/Grid'
import type { TestResult } from '../../api/models'

const fmt2 = (n?: number) => (typeof n === 'number' && Number.isFinite(n) ? n.toFixed(2) : '—')
const fmt0 = (n?: number) => (typeof n === 'number' && Number.isFinite(n) ? Math.round(n).toString() : '—')

function getScores(r: TestResult) {
  const x = r as Record<string, any>
  const n = (v: any) => (Number.isFinite(Number(v)) ? Number(v) : 0)
  return { rel: n(x.relevance), fact: n(x.factual_accuracy), comp: n(x.completeness), tone: n(x.tone), compr: n(x.comprehensibility) }
}
function pqsRaw(r: TestResult): number {
  const s = getScores(r); const vals = [s.rel, s.fact, s.comp, s.tone, s.compr]
  if (vals.some(v => v <= 0)) return 0
  return vals.reduce((a, b) => a * b, 1)
}
function pqsNorm(r: TestResult): number {
  const raw = pqsRaw(r); return raw > 0 ? Math.pow(raw, 1 / 5) : 0
}
function scoreColor(n: number): ChipProps['color'] {
  if (!Number.isFinite(n)) return 'default'
  if (n >= 4.5) return 'success'
  if (n >= 3.5) return 'info'
  if (n >= 2.5) return 'warning'
  return 'error'
}
const short = (t: string, max = 120) => {
  if (!t) return ''
  const s = t.trim(); if (s.length <= max) return s
  const cut = s.slice(0, max).replace(/\s+\S*$/, '')
  return `${cut}…`
}

function ClampText({ text, lines = 2, title }: { text: string; lines?: number; title?: string }) {
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
          wordBreak: 'break-word',
        }}
      >
        {text}
      </Typography>
    </Tooltip>
  )
}

/** Header: Abkürzung + deutsche Bezeichnung (zweizeilig, ohne Überlappung) */
const HeadLabel: React.FC<{ abbr: string; label: string; align?: 'left'|'center'|'right' }> = ({ abbr, label, align = 'center' }) => (
  <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: align, lineHeight: 1.15, width: '100%' }}>
    <Typography variant="body2" sx={{ fontWeight: 600 }}>{abbr}</Typography>
    <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
      {label}
    </Typography>
  </Box>
)

/** einheitliche Breite für Score-Spalten */
const SCORE_TH_SX = { width: 88, maxWidth: 88, px: 1 }
const SCORE_TD_SX = { width: 88, maxWidth: 88, px: 1, textAlign: 'center' as const }
/** Chip-Style: tabulare Ziffern, nie abgeschnitten */
const SCORE_CHIP_SX = {
  fontFamily: 'Roboto Mono, monospace',
  fontVariantNumeric: 'tabular-nums',
  '& .MuiChip-label': { px: 1, maxWidth: 'none' },
} as const

type RowProps = {
  r: TestResult
  dense?: boolean
  onEdit: (r: TestResult) => void
  expandSignal?: { action: 'expand'|'collapse'; seq: number }
}

const ResultRow: React.FC<RowProps> = ({ r, onEdit, expandSignal }) => {
  const [open, setOpen] = React.useState(false)

  React.useEffect(() => {
    if (!expandSignal) return
    setOpen(expandSignal.action === 'expand')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandSignal?.seq])

  const { rel, fact, comp, tone, compr } = getScores(r)
  const pqs  = pqsRaw(r)
  const pqsN = pqsNorm(r)

  return (
    <>
      <TableRow hover>
        <TableCell padding="checkbox" sx={{ width: 40 }}>
          <IconButton size="small" onClick={() => setOpen(s => !s)} aria-label={open ? 'Zuklappen' : 'Aufklappen'}>
            {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
          </IconButton>
        </TableCell>

        {/* Prompt (flexibel) */}
        <TableCell
          sx={{
            width: { xs: '48%', md: '34%' },
            maxWidth: { md: 560 },
            pr: 2,
          }}
        >
          <Box sx={{ mb: 0.5 }}>
            <ClampText text={r.prompt_text} lines={2} />
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            Golden: {short(r.golden_answer, 140)}
          </Typography>
        </TableCell>

        {/* AI-Antwort (flexibel) */}
        <TableCell
          sx={{
            width: { xs: '52%', md: '36%' },
            maxWidth: { md: 620 },
            pr: 2,
          }}
        >
          <ClampText text={r.ai_response} lines={2} />
        </TableCell>

        {/* Scores – ab md sichtbar */}
        <TableCell sx={{ ...SCORE_TD_SX, display: { xs: 'none', md: 'table-cell' } }}>
          <Chip size="small" label={fmt2(rel)}  color={scoreColor(rel)}  sx={SCORE_CHIP_SX} />
        </TableCell>
        <TableCell sx={{ ...SCORE_TD_SX, display: { xs: 'none', md: 'table-cell' } }}>
          <Chip size="small" label={fmt2(fact)} color={scoreColor(fact)} sx={SCORE_CHIP_SX} />
        </TableCell>
        <TableCell sx={{ ...SCORE_TD_SX, display: { xs: 'none', md: 'table-cell' } }}>
          <Chip size="small" label={fmt2(comp)} color={scoreColor(comp)} sx={SCORE_CHIP_SX} />
        </TableCell>
        <TableCell sx={{ ...SCORE_TD_SX, display: { xs: 'none', md: 'table-cell' } }}>
          <Chip size="small" label={fmt2(tone)} color={scoreColor(tone)} sx={SCORE_CHIP_SX} />
        </TableCell>
        <TableCell sx={{ ...SCORE_TD_SX, display: { xs: 'none', md: 'table-cell' } }}>
          <Chip size="small" label={fmt2(compr)} color={scoreColor(compr)} sx={SCORE_CHIP_SX} />
        </TableCell>

        {/* PQS bleibt immer sichtbar */}
        <TableCell sx={SCORE_TD_SX}>
          <Chip size="small" label={fmt0(pqs)} color={scoreColor(pqsN)} sx={SCORE_CHIP_SX} />
        </TableCell>

        <TableCell align="right" sx={{ whiteSpace: 'nowrap', width: 84 }}>
          <IconButton color="primary" onClick={() => onEdit(r)} aria-label="Bearbeiten">
            <EditIcon />
          </IconButton>
        </TableCell>
      </TableRow>

      {/* Expanded content */}
      <TableRow>
        {/* colSpan: 1 (expand) + 2 (texte) + 5 (scores) + 1 (PQS) + 1 (aktion) = 10 */}
        <TableCell colSpan={10} sx={{ p: 0, border: 0 }}>
          <Collapse in={open} timeout="auto" unmountOnExit>
            <Box sx={{ p: 2, bgcolor: (t) => t.palette.action.hover, borderTop: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
              <Grid container spacing={2} sx={{ width: '100%' }}>
                <Grid size={{ xs: 12 }}>
                  <Typography variant="subtitle2">Prompt</Typography>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{r.prompt_text}</Typography>
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <Typography variant="subtitle2">Golden Answer</Typography>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{r.golden_answer}</Typography>
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <Typography variant="subtitle2">AI-Antwort</Typography>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{r.ai_response}</Typography>
                </Grid>

                <Grid size={{ xs: 12 }}><Divider sx={{ my: 1 }} /></Grid>

                <Grid size={{ xs: 12 }}>
                  <Typography variant="caption" color="text.secondary">
                    PQS = Produkt der fünf Kategorien (1–5). Rohwert 1…3125.
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 0.5 }}>
                    PQS: <strong>{fmt0(pqs)}</strong>
                  </Typography>
                </Grid>

                {Boolean((r as any).relevance_comment) && (
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Typography variant="caption" color="text.secondary">Relevanz – Kommentar</Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{(r as any).relevance_comment}</Typography>
                  </Grid>
                )}
                {Boolean((r as any).factual_accuracy_comment) && (
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Typography variant="caption" color="text.secondary">Faktentreue – Kommentar</Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{(r as any).factual_accuracy_comment}</Typography>
                  </Grid>
                )}
                {Boolean((r as any).completeness_comment) && (
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Typography variant="caption" color="text.secondary">Vollständigkeit – Kommentar</Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{(r as any).completeness_comment}</Typography>
                  </Grid>
                )}
                {Boolean((r as any).tone_comment) && (
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Typography variant="caption" color="text.secondary">Tonalität – Kommentar</Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{(r as any).tone_comment}</Typography>
                  </Grid>
                )}
                {Boolean((r as any).comprehensibility_comment) && (
                  <Grid size={{ xs: 12 }}>
                    <Typography variant="caption" color="text.secondary">Verständlichkeit – Kommentar</Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{(r as any).comprehensibility_comment}</Typography>
                  </Grid>
                )}
                {Boolean((r as any).overall_comment) && (
                  <Grid size={{ xs: 12 }}>
                    <Divider sx={{ my: 1 }} />
                    <Typography variant="caption" color="text.secondary">Gesamt-Kommentar</Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{(r as any).overall_comment}</Typography>
                  </Grid>
                )}
              </Grid>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  )
}

type TableProps = {
  results: TestResult[]
  dense?: boolean
  onEdit: (r: TestResult) => void
  expandSignal?: { action: 'expand'|'collapse'; seq: number }
}

const ResultsTable: React.FC<TableProps> = ({ results, dense, onEdit, expandSignal }) => {
  return (
    <TableContainer sx={{ width: '100%', overflowX: 'hidden' }}>
      <Table
        size={dense ? 'small' : 'medium'}
        aria-label="results table"
        sx={{ tableLayout: 'fixed', width: '100%' }}
      >
        <TableHead>
          <TableRow>
            <TableCell sx={{ width: 40 }} />
            <TableCell sx={{ width: { xs: '48%', md: '34%' } }}>
              <HeadLabel abbr="Prompt" label="Eingabe" align="left" />
            </TableCell>
            <TableCell sx={{ width: { xs: '52%', md: '36%' } }}>
              <HeadLabel abbr="AI-Antwort" label="Modelloutput" align="left" />
            </TableCell>
            <TableCell align="center" sx={{ ...SCORE_TH_SX, display: { xs: 'none', md: 'table-cell' } }}>
              <Tooltip title="Relevanz"><span><HeadLabel abbr="Rel." label="Relevanz" /></span></Tooltip>
            </TableCell>
            <TableCell align="center" sx={{ ...SCORE_TH_SX, display: { xs: 'none', md: 'table-cell' } }}>
              <Tooltip title="Faktentreue"><span><HeadLabel abbr="Fak." label="Faktentreue" /></span></Tooltip>
            </TableCell>
            <TableCell align="center" sx={{ ...SCORE_TH_SX, display: { xs: 'none', md: 'table-cell' } }}>
              <Tooltip title="Vollständigkeit"><span><HeadLabel abbr="Vst." label="Vollständigkeit" /></span></Tooltip>
            </TableCell>
            <TableCell align="center" sx={{ ...SCORE_TH_SX, display: { xs: 'none', md: 'table-cell' } }}>
              <Tooltip title="Tonalität"><span><HeadLabel abbr="Ton." label="Tonalität" /></span></Tooltip>
            </TableCell>
            <TableCell align="center" sx={{ ...SCORE_TH_SX, display: { xs: 'none', md: 'table-cell' } }}>
              <Tooltip title="Verständlichkeit"><span><HeadLabel abbr="Vstl." label="Verständlichkeit" /></span></Tooltip>
            </TableCell>
            <TableCell align="center" sx={SCORE_TH_SX}>
              <Tooltip title="Prompting Quality Score (Produkt)"><span><HeadLabel abbr="PQS" label="Score" /></span></Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ width: 84 }}>
              <HeadLabel abbr="Aktion" label="Bearbeiten" align="right" />
            </TableCell>
          </TableRow>
        </TableHead>

        <TableBody>
          {results.map((r) => (
            <ResultRow key={r.id} r={r} onEdit={onEdit} expandSignal={expandSignal} />
          ))}
          {(!results || results.length === 0) && (
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
  )
}

export default ResultsTable
