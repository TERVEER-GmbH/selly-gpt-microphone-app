// src/components/run-detail/RunHeader.tsx
import React from 'react'
import {
  Box,
  Button,
  Chip,
  LinearProgress,
  Paper,
  Stack,
  Typography,
  Tooltip,
} from '@mui/material'
import Grid from '@mui/material/Grid'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import RefreshIcon from '@mui/icons-material/Refresh'
import DriveFileRenameOutlineIcon from '@mui/icons-material/DriveFileRenameOutline'
import { Link as RouterLink } from 'react-router-dom'
import type { RunStatus } from '../../api/models'

type Props = {
  runId: string
  status: RunStatus | null
  onRefresh: () => void
  onOpenRename: () => void
}

const mono = { fontFamily: 'Roboto Mono, ui-monospace, SFMono-Regular, Menlo, monospace' }

const RunHeader: React.FC<Props> = ({ runId, status, onRefresh, onOpenRename }) => {
  const total = status?.total ?? 0
  const completed = status?.completed ?? 0
  const progress = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0

  const model = status?.params?.model ?? '—'
  const temperature = status?.params?.temperature ?? '—'
  const maxTokens = status?.params?.max_tokens ?? '—'
  const topP = (status as any)?.params?.top_p // optional/falls vorhanden

  return (
    <Box sx={{ pt: 3, pb: 2 }}>
      {/* Top-Bar: Back + Actions */}
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Button component={RouterLink} to="/admin/runs" startIcon={<ArrowBackIcon />}>
          Zurück zur Übersicht
        </Button>
        <Box sx={{ flexGrow: 1 }} />
        <Button onClick={onRefresh} startIcon={<RefreshIcon />} variant="outlined">
          Aktualisieren
        </Button>
      </Stack>

      {/* Bubble */}
      <Paper
        variant="outlined"
        sx={{
          p: 2,
          borderRadius: 2,
          bgcolor: (t) => (t.palette.mode === 'light' ? t.palette.grey[50] : 'transparent'),
        }}
      >
        <Grid container spacing={2} sx={{ width: '100%' }}>
          {/* Titel & Rename */}
          <Grid size={{ xs: 12 }}>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
              <Typography variant="h5" sx={{ mr: 1 }}>
                {status?.name || `Run ${status?.run_id ?? runId}`}
              </Typography>
              <Button
                size="small"
                startIcon={<DriveFileRenameOutlineIcon />}
                onClick={onOpenRename}
              >
                Namen ändern
              </Button>
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              Run-ID: <span style={mono as any}>{status?.run_id ?? runId}</span>
            </Typography>
          </Grid>

          {/* Parameter-Chips */}
          <Grid size={{ xs: 12, md: 8 }}>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              <Chip label={`Model: ${model}`} size="small" />
              <Chip label={`Temp: ${temperature}`} size="small" />
              <Chip label={`Max Tokens: ${maxTokens}`} size="small" />
              {topP != null && <Chip label={`Top-p: ${topP}`} size="small" />}
              {status?.created_at && (
                <Chip
                  size="small"
                  label={`Erstellt: ${new Date(status.created_at).toLocaleString()}`}
                />
              )}
            </Stack>
          </Grid>

          {/* Status + Progress */}
          <Grid size={{ xs: 12, md: 4 }}>
            <Stack spacing={0.75}>
              <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-start">
                <Chip
                  size="small"
                  label={status?.status ?? '—'}
                  color={
                    status?.status === 'Done'
                      ? 'success'
                      : status?.status === 'Running'
                      ? 'info'
                      : 'default'
                  }
                />
                <Typography variant="body2" sx={mono}>
                  {completed} / {total}
                </Typography>
                <Tooltip title="Fortschritt">
                  <Typography variant="body2" color="text.secondary">
                    {progress}%
                  </Typography>
                </Tooltip>
              </Stack>
              {status && status.status !== 'Done' && (
                <LinearProgress
                  variant="determinate"
                  value={progress}
                  sx={{ height: 8, borderRadius: 1 }}
                />
              )}
            </Stack>
          </Grid>
        </Grid>
      </Paper>
    </Box>
  )
}

export default RunHeader
