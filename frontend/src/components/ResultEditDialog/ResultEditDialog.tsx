// src/components/ResultEditDialog/ResultEditDialog.tsx
import React from 'react'
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, TextField, Typography, Box, Stack
} from '@mui/material'
import type { TestResult, TestResultUpdate } from '../../api/models'

type ScoreKey =
  | 'relevance'
  | 'factual_accuracy'
  | 'completeness'
  | 'tone'
  | 'comprehensibility'

type CommentKey =
  | 'relevance_comment'
  | 'factual_accuracy_comment'
  | 'completeness_comment'
  | 'tone_comment'
  | 'comprehensibility_comment'

type Props = {
  open: boolean
  initial: TestResult
  onClose: () => void
  onSave: (patch: TestResultUpdate) => Promise<void> | void
  saving?: boolean
}

// --- Helpers (1–5) ---
const clamp15 = (n: number) => Math.max(1, Math.min(5, Math.round(n)))
const parse15 = (s: string): number | null => {
  const n = Number(s.trim())
  if (!Number.isFinite(n)) return null
  if (n < 1 || n > 5) return null
  return n
}
// WICHTIG: immer string zurückgeben
const toStr = (v: unknown): string => (
  typeof v === 'number' ? String(v)
  : typeof v === 'string' ? v
  : ''
)

type FormState = {
  relevance: string
  relevance_comment: string
  factual_accuracy: string
  factual_accuracy_comment: string
  completeness: string
  completeness_comment: string
  tone: string
  tone_comment: string
  comprehensibility: string
  comprehensibility_comment: string
  overall_comment: string
}

// --------- Memoized Row (fokus-sicher) ----------
type ScoreRowProps = {
  label: string
  score: string
  comment: string
  invalid: boolean
  onScoreChange: (v: string) => void
  onScoreBlur: () => void
  onCommentChange: (v: string) => void
}
const ScoreRow = React.memo(function ScoreRow (props: ScoreRowProps) {
  const { label, score, comment, invalid, onScoreChange, onScoreBlur, onCommentChange } = props
  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ width: '100%' }}>
      <TextField
        sx={{ width: { xs: '100%', sm: 220 } }}
        type="text"
        inputMode="numeric"
        label={`${label} (1–5)`}
        value={score}
        onChange={(e) => onScoreChange(e.currentTarget.value)}
        onBlur={onScoreBlur}
        error={invalid}
        helperText={invalid ? 'Wert 1–5 (ganze Zahl)' : ' '}
      />
      <TextField
        fullWidth
        multiline
        minRows={2}
        label={`${label} – Kommentar`}
        value={comment}
        onChange={(e) => onCommentChange(e.currentTarget.value)}
      />
    </Stack>
  )
})

export default function ResultEditDialog({
  open,
  initial,
  onClose,
  onSave,
  saving = false
}: Props) {
  // Snapshot aus initial ableiten
  const initialForm = React.useMemo<FormState>(() => {
    const x = initial as unknown as Record<string, any>
    return {
      relevance: toStr(x.relevance ?? 3),
      relevance_comment: toStr(x.relevance_comment ?? ''),
      factual_accuracy: toStr(x.factual_accuracy ?? 3),
      factual_accuracy_comment: toStr(x.factual_accuracy_comment ?? ''),
      completeness: toStr(x.completeness ?? 3),
      completeness_comment: toStr(x.completeness_comment ?? ''),
      tone: toStr(x.tone ?? 3),
      tone_comment: toStr(x.tone_comment ?? ''),
      comprehensibility: toStr(x.comprehensibility ?? 3),
      comprehensibility_comment: toStr(x.comprehensibility_comment ?? ''),
      overall_comment: toStr(x.overall_comment ?? ''),
    }
  }, [initial])

  // State **ohne** Inline-Funktion initialisieren (vermeidet den TS-Fehler)
  const [form, setForm] = React.useState<FormState>(initialForm)

  // Nur resetten, wenn eine andere Result-ID kommt
  const lastIdRef = React.useRef<string>(initial.id)
  React.useEffect(() => {
    if (initial.id !== lastIdRef.current) {
      lastIdRef.current = initial.id
      setForm(initialForm)
    }
  }, [initial.id, initialForm])

  // Stabile Handler
  const makeScoreChange = React.useCallback(
    (key: ScoreKey) => (v: string) => setForm(prev => ({ ...prev, [key]: v })),
    []
  )
  const makeScoreBlur = React.useCallback(
    (key: ScoreKey) => () => {
      const parsed = parse15(form[key])
      setForm(prev => ({ ...prev, [key]: parsed == null ? '3' : String(clamp15(parsed)) }))
    },
    [form]
  )
  const makeCommentChange = React.useCallback(
    (key: CommentKey) => (v: string) => setForm(prev => ({ ...prev, [key]: v })),
    []
  )

  const allValid = (['relevance','factual_accuracy','completeness','tone','comprehensibility'] as ScoreKey[])
    .every(k => parse15(form[k]) != null)
  const canSave = allValid && !saving

  const handleSave = async () => {
    const toNum = (s: string) => clamp15(parse15(s) ?? 3)
    const patch: TestResultUpdate = {
      relevance: toNum(form.relevance),
      relevance_comment: form.relevance_comment.trim(),
      factual_accuracy: toNum(form.factual_accuracy),
      factual_accuracy_comment: form.factual_accuracy_comment.trim(),
      completeness: toNum(form.completeness),
      completeness_comment: form.completeness_comment.trim(),
      tone: toNum(form.tone),
      tone_comment: form.tone_comment.trim(),
      comprehensibility: toNum(form.comprehensibility),
      comprehensibility_comment: form.comprehensibility_comment.trim(),
      overall_comment: form.overall_comment.trim(),
    }
    await onSave(patch)
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="md"
      disableAutoFocus
      keepMounted
    >
      <DialogTitle>Ergebnis korrigieren (Skala 1–5)</DialogTitle>
      <DialogContent dividers>
        <Box mb={2}>
          <Typography variant="body2" color="text.secondary">
            Wertebereich für Scores: 1 – 5. Kommentare sind optional.
          </Typography>
        </Box>

        <Stack spacing={2}>
          <ScoreRow
            label="Relevanz"
            score={form.relevance}
            comment={form.relevance_comment}
            invalid={parse15(form.relevance) == null}
            onScoreChange={makeScoreChange('relevance')}
            onScoreBlur={makeScoreBlur('relevance')}
            onCommentChange={makeCommentChange('relevance_comment')}
          />
          <ScoreRow
            label="Faktentreue"
            score={form.factual_accuracy}
            comment={form.factual_accuracy_comment}
            invalid={parse15(form.factual_accuracy) == null}
            onScoreChange={makeScoreChange('factual_accuracy')}
            onScoreBlur={makeScoreBlur('factual_accuracy')}
            onCommentChange={makeCommentChange('factual_accuracy_comment')}
          />
          <ScoreRow
            label="Vollständigkeit"
            score={form.completeness}
            comment={form.completeness_comment}
            invalid={parse15(form.completeness) == null}
            onScoreChange={makeScoreChange('completeness')}
            onScoreBlur={makeScoreBlur('completeness')}
            onCommentChange={makeCommentChange('completeness_comment')}
          />
          <ScoreRow
            label="Tonalität"
            score={form.tone}
            comment={form.tone_comment}
            invalid={parse15(form.tone) == null}
            onScoreChange={makeScoreChange('tone')}
            onScoreBlur={makeScoreBlur('tone')}
            onCommentChange={makeCommentChange('tone_comment')}
          />
          <ScoreRow
            label="Verständlichkeit"
            score={form.comprehensibility}
            comment={form.comprehensibility_comment}
            invalid={parse15(form.comprehensibility) == null}
            onScoreChange={makeScoreChange('comprehensibility')}
            onScoreBlur={makeScoreBlur('comprehensibility')}
            onCommentChange={makeCommentChange('comprehensibility_comment')}
          />

          <TextField
            fullWidth
            multiline
            minRows={3}
            label="Gesamt-Kommentar"
            value={form.overall_comment}
            onChange={(e) => setForm(prev => ({ ...prev, overall_comment: e.currentTarget.value }))}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Abbrechen</Button>
        <Button onClick={handleSave} disabled={!canSave} variant="contained">
          {saving ? 'Speichern…' : 'Speichern'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
