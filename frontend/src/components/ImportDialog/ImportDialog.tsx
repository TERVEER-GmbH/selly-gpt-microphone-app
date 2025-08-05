import React, { useRef, useState } from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  TableContainer,
  Paper,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody
} from '@mui/material'

interface Props {
  open: boolean
  onClose: () => void
  onImport: (file: File) => Promise<void>
}

const ImportDialog: React.FC<Props> = ({ open, onClose, onImport }) => {
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<any[]>([])
  const [errors, setErrors] = useState<{ line: number; error: string }[]>([])

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null
    setFile(f)
    if (!f) return
    // Preview-API
    const form = new FormData()
    form.append('file', f)
    try {
      const resp = await fetch('/admin/prompts/import?preview=true', { // optional preview query
        method: 'POST',
        body: form
      })
      const json = await resp.json()
      setPreview(json.created || [])
      setErrors(json.errors || [])
    } catch {
      setErrors([{ line: 0, error: 'Preview fehlgeschlagen' }])
    }
  }

  const handleImport = () => {
    if (file) {
      onImport(file).then(onClose)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Prompts importieren</DialogTitle>
      <DialogContent dividers>
        <Button variant="outlined" component="label">
          Datei wählen
          <input hidden type="file" accept=".csv,.json" onChange={handleFileChange} ref={fileRef} />
        </Button>

        {preview.length > 0 && (
          <Box mt={2}>
            <Typography variant="subtitle1">Vorschau</Typography>
            <TableContainer component={Paper}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {Object.keys(preview[0]).map((h) => (
                      <TableCell key={h}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {preview.slice(0, 5).map((row, i) => (
                    <TableRow key={i}>
                      {Object.values(row).map((v, j) => (
                        <TableCell key={j}>{String(v)}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Box>
        )}

        {errors.length > 0 && (
          <Box mt={2}>
            <Typography variant="subtitle1" color="error">
              Fehler
            </Typography>
            {errors.map((err) => (
              <Typography key={err.line} variant="body2" color="error">
                Zeile {err.line}: {err.error}
              </Typography>
            ))}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Abbrechen</Button>
        <Button
          variant="contained"
          onClick={handleImport}
          disabled={!file || errors.length > 0}
        >
          Importieren
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export default ImportDialog
