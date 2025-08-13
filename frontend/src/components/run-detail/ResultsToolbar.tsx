import React from 'react'
import { Box, Button, Paper, Stack, Switch, TextField, FormControlLabel } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'

type Props = {
  query: string
  onQuery: (q: string) => void
  dense: boolean
  onDense: (v: boolean) => void
  onExpandAll: () => void
  onCollapseAll: () => void
}

const ResultsToolbar: React.FC<Props> = ({ query, onQuery, dense, onDense, onExpandAll, onCollapseAll }) => {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ xs: 'stretch', md: 'center' }}>
        <TextField
          size="small"
          label="Suchen in Prompt / Antwort / Golden…"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          sx={{ minWidth: 320 }}
        />
        <Box sx={{ flexGrow: 1 }} />
        <FormControlLabel
          control={<Switch size="small" checked={dense} onChange={(_, v)=>onDense(v)} />}
          label="Kompakt"
        />
        <Button size="small" startIcon={<ExpandMoreIcon />} onClick={onExpandAll}>Alle öffnen</Button>
        <Button size="small" startIcon={<ExpandLessIcon />} onClick={onCollapseAll}>Alle schließen</Button>
      </Stack>
    </Paper>
  )
}
export default ResultsToolbar
