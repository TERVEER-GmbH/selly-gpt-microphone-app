// src/components/BatchTestDialog/BatchTestDialog.tsx
import React, { useState, useEffect } from 'react'
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
  TextField
} from '@mui/material'
import type { Prompt, TestParams } from '../../api/models'

interface Props {
  open: boolean
  prompts: Prompt[]
  initialSelected: string[]
  params: TestParams
  onParamsChange: (p: TestParams) => void
  onStart: (ids: string[], params: TestParams) => void
  onClose: () => void
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

  useEffect(() => {
    setSelected(initialSelected)
  }, [initialSelected, open])

  const toggle = (id: string) => {
    setSelected(s =>
      s.includes(id) ? s.filter(x => x !== id) : [...s, id]
    )
  }

  const handleParamChange =
    (field: keyof TestParams) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onParamsChange({ ...params, [field]: e.target.value })
    }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Batch-Test konfigurieren</DialogTitle>
      <DialogContent>
        <List>
          {prompts.map(p => (
            <ListItem key={p.id} disablePadding>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={selected.includes(p.id)}
                    onChange={() => toggle(p.id)}
                  />
                }
                label={p.text}
              />
            </ListItem>
          ))}
        </List>

        <Stack spacing={2} mt={2}>
          <TextField
            label="Modell"
            value={params.model}
            fullWidth
            onChange={handleParamChange('model')}
          />
          <TextField
            label="Temperatur"
            type="number"
            value={params.temperature}
            fullWidth
            onChange={handleParamChange('temperature')}
          />
          <TextField
            label="Max Tokens"
            type="number"
            value={params.max_tokens}
            fullWidth
            onChange={handleParamChange('max_tokens')}
          />
          <TextField
            label="Top-p"
            type="number"
            value={params.top_p}
            fullWidth
            onChange={handleParamChange('top_p')}
          />
        </Stack>
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>Abbrechen</Button>
        <Button
          variant="contained"
          onClick={() => onStart(selected, params)}
          disabled={selected.length === 0}
        >
          Batch starten
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export default BatchTestDialog
