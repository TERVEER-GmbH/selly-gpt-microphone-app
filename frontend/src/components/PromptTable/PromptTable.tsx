import React from 'react'
import {
  TableContainer,
  Paper,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  IconButton
} from '@mui/material'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import type { Prompt } from '../../api/models'

interface Props {
  prompts: Prompt[]
  onEdit: (p: Prompt) => void
  onDelete: (id: string) => void
}

const PromptTable: React.FC<Props> = ({ prompts, onEdit, onDelete }) => (
  <TableContainer component={Paper} sx={{ mt: 2 }}>
    <Table>
      <TableHead>
        <TableRow>
          <TableCell>Text</TableCell>
          <TableCell>Golden Answer</TableCell>
          <TableCell>Tags</TableCell>
          <TableCell align="right">Aktionen</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {prompts.map((p) => (
          <TableRow key={p.id} hover>
            <TableCell>{p.text}</TableCell>
            <TableCell>{p.golden_answer}</TableCell>
            <TableCell>{p.tags.join(', ')}</TableCell>
            <TableCell align="right">
              <IconButton size="small" onClick={() => onEdit(p)}><EditIcon /></IconButton>
              <IconButton size="small" onClick={() => onDelete(p.id)}><DeleteIcon /></IconButton>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </TableContainer>
)

export default PromptTable
