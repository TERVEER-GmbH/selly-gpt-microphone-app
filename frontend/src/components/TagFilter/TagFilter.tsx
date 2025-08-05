import React from 'react'
import { Autocomplete, TextField } from '@mui/material'

interface Props {
  tags: string[]
  onFilter: (tag?: string) => void
}

const TagFilter: React.FC<Props> = ({ tags, onFilter }) => (
  <Autocomplete
    options={['Alle', ...tags]}
    onChange={(_, v) => {
      // wenn kein Wert oder "Alle" ausgewählt → kein Filter
      if (!v || v === 'Alle') {
        onFilter(undefined)
      } else {
        onFilter(v)
      }
    }}
    renderInput={(params) => <TextField {...params} label="Nach Tag filtern" size="small" />}
    sx={{ width: 200 }}
  />
)

export default TagFilter
