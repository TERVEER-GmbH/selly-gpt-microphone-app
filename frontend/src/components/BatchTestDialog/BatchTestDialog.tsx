// src/components/BatchTestDialog/BatchTestDialog.tsx
import React, { useState, useEffect, useMemo } from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  List,
  ListItem,
  Checkbox,
  FormControlLabel,
  Stack,
  TextField,
  Box,
  Divider,
  Typography,
  Chip,
  Paper
} from '@mui/material'
import type { Prompt, TestParams } from '../../api/models'

interface Props {
  open: boolean
  prompts: Prompt[]
  initialSelected: string[]
  params: TestParams
  onParamsChange: (p: TestParams) => void
  onStart: (ids: string[], params: TestParams, name?: string) => void
  onClose: () => void
}

/** Schöner Default-Name wie im Backend (ohne Run-ID, die kennen wir hier noch nicht). */
function defaultRunName(promptCount: number, model?: string) {
  const dt = new Date()
  const date = dt.toLocaleDateString()
  const time = dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const short = Math.random().toString(16).slice(2, 6)
  const mdl = model || 'model'
  return `${date} • ${time} • ${mdl} • ${promptCount} Prompts • ${short}`
}

const BatchTestDialog: React.FC<Props> = ({
  open,
  prompts,
  initialSelected,
  params,
  onParamsChange,
  onStart,
  onClose
}) => {
  const [selected, setSelected] = useState<string[]>([])
  const [runName, setRunName] = useState<string>('')
  const [nameDirty, setNameDirty] = useState<boolean>(false)

  // Selektion initialisieren
  useEffect(() => {
    setSelected(initialSelected)
  }, [initialSelected, open])

  // Default-Name automatisch setzen/aktualisieren (solange der User ihn nicht editiert hat)
  useEffect(() => {
    if (!nameDirty) {
      setRunName(defaultRunName(selected.length, params.model))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected.length, params.model, open])

  const allSelected = selected.length > 0 && selected.length === prompts.length
  const partialSelected = selected.length > 0 && selected.length < prompts.length

  const toggle = (id: string) => {
    setSelected(s => (s.includes(id) ? s.filter(x => x !== id) : [...s, id]))
  }
  const toggleAll = () => {
    if (allSelected) setSelected([])
    else setSelected(prompts.map(p => p.id))
  }

  // Zahlfelder sauber in Number konvertieren
  const handleText = (field: keyof TestParams) => (e: React.ChangeEvent<HTMLInputElement>) => {
    onParamsChange({ ...params, [field]: e.target.value })
  }
  const handleNum = (field: keyof TestParams) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value === '' ? undefined : Number(e.target.value)
    onParamsChange({ ...params, [field]: v as any })
  }

  // hübsche, kompakte Liste (nur Auszug)
  const sortedPrompts = useMemo(() => prompts.slice(), [prompts])

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>
        Batch-Test konfigurieren
        <Typography variant="body2" color="text.secondary">
          Wähle Prompts, vergib einen sprechenden Namen und passe die Modell-Parameter an.
        </Typography>
      </DialogTitle>

      <DialogContent dividers>
        {/* Name + Auswahlstatus */}
        <Stack spacing={1.5} sx={{ mb: 2 }}>
          <TextField
            label="Name des Runs"
            value={runName}
            onChange={e => {
              setRunName(e.target.value)
              setNameDirty(true)
            }}
            placeholder={defaultRunName(initialSelected.length, params.model)}
            fullWidth
          />
          <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
            <Chip size="small" label={`Ausgewählt: ${selected.length}`} />
            <Chip size="small" variant="outlined" label={`Gesamt: ${prompts.length}`} />
            {params.model && <Chip size="small" variant="outlined" label={`Modell: ${params.model}`} />}
          </Stack>
        </Stack>

        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          {/* Prompt-Auswahl */}
          <Paper variant="outlined" sx={{ p: 1.5, flex: 1, minHeight: 340 }}>
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
              <Typography variant="subtitle2">Prompts</Typography>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={allSelected}
                    indeterminate={partialSelected}
                    onChange={toggleAll}
                  />
                }
                label="Alle auswählen"
              />
            </Stack>

            <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, maxHeight: 260, overflow: 'auto' }}>
              <List dense disablePadding>
                {sortedPrompts.map(p => (
                  <ListItem key={p.id} disableGutters sx={{ px: 1 }}>
                    <FormControlLabel
                      sx={{
                        alignItems: 'flex-start',
                        m: 0,
                        py: 0.5,
                        '& .MuiFormControlLabel-label': {
                          overflow: 'hidden',
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical'
                        }
                      }}
                      control={
                        <Checkbox
                          size="small"
                          checked={selected.includes(p.id)}
                          onChange={() => toggle(p.id)}
                        />
                      }
                      label={p.text}
                    />
                  </ListItem>
                ))}
              </List>
            </Box>
          </Paper>

          {/* Model-Parameter */}
          <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Modell-Parameter
            </Typography>
            <Stack spacing={1.5}>
              <TextField
                label="Modell"
                value={params.model ?? ''}
                onChange={handleText('model')}
                fullWidth
              />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                <TextField
                  label="Temperatur"
                  type="number"
                  inputProps={{ step: '0.1', min: '0', max: '2' }}
                  value={params.temperature ?? ''}
                  onChange={handleNum('temperature')}
                  fullWidth
                />
                <TextField
                  label="Top-p"
                  type="number"
                  inputProps={{ step: '0.05', min: '0', max: '1' }}
                  value={params.top_p ?? ''}
                  onChange={handleNum('top_p')}
                  fullWidth
                />
              </Stack>
              <TextField
                label="Max Tokens"
                type="number"
                inputProps={{ step: '1', min: '1' }}
                value={params.max_tokens ?? ''}
                onChange={handleNum('max_tokens')}
                fullWidth
              />

              <Divider sx={{ my: 1 }} />

              {/* Platzhalter: System Prompt (ausgegraut) */}
              <Box
                sx={{
                  p: 1,
                  borderRadius: 1,
                  bgcolor: theme => theme.palette.action.disabledBackground,
                  border: '1px dashed',
                  borderColor: 'divider'
                }}
              >
                <TextField
                  label="System Prompt (bald verfügbar)"
                  placeholder="Hier kannst du später einen globalen System-Prompt für den gesamten Batch hinterlegen."
                  multiline
                  minRows={3}
                  fullWidth
                  disabled
                />
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                  Dieser Bereich ist deaktiviert. Coming soon ✨
                </Typography>
              </Box>
            </Stack>
          </Paper>
        </Stack>
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>Abbrechen</Button>
        <Button
          variant="contained"
          onClick={() => onStart(selected, params, runName.trim() || undefined)}
          disabled={selected.length === 0}
        >
          Batch starten
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export default BatchTestDialog
