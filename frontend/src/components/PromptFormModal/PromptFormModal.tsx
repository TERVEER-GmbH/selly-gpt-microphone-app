import React, { useState, useEffect } from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Chip,
  Stack,
  Autocomplete
} from '@mui/material'
import type { Prompt } from '../../api/models'

interface Props {
  open: boolean
  prompt?: Prompt
  onClose: () => void
  onSubmit: (data: { text: string; golden_answer: string; tags: string[] }) => void
}

const PromptFormModal: React.FC<Props> = ({ open, prompt, onClose, onSubmit }) => {
  const [text, setText] = useState('')
  const [golden, setGolden] = useState('')
  const [tags, setTags] = useState<string[]>([])

  useEffect(() => {
    if (prompt) {
      setText(prompt.text)
      setGolden(prompt.golden_answer)
      setTags(prompt.tags)
    } else {
      setText('')
      setGolden('')
      setTags([])
    }
  }, [prompt, open])

  const handleSave = () => {
    onSubmit({ text, golden_answer: golden, tags })
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{prompt ? 'Prompt bearbeiten' : 'Neuen Prompt anlegen'}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Prompt Text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            fullWidth
          />
          <TextField
            label="Golden Answer"
            value={golden}
            onChange={(e) => setGolden(e.target.value)}
            fullWidth
          />
          <Autocomplete
            multiple
            freeSolo
            options={[]} // später kannst du hier alle Tags vorschlagen
            value={tags}
            onChange={(_, v) => setTags(v)}
            renderTags={(value: readonly string[], getTagProps) =>
              value.map((option, index) => (
                <Chip variant="outlined" label={option} {...getTagProps({ index })} />
              ))
            }
            renderInput={(params) => <TextField {...params} label="Tags" />}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Abbrechen</Button>
        <Button variant="contained" onClick={handleSave} disabled={!text || !golden}>
          Speichern
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export default PromptFormModal
