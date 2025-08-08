import React from 'react'
import {
  TableContainer,
  Paper,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  IconButton,
  Menu,
  MenuItem,
  Checkbox
} from '@mui/material'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import MoreVertIcon from '@mui/icons-material/MoreVert'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import type { Prompt } from '../../api/models'

interface Props {
  prompts: Prompt[]
  selectedIds: string[]
  onSelect: (ids: string[]) => void
  onEdit: (p: Prompt) => void
  onDelete: (id: string) => void
  onTest: (id: string) => void
}

const PromptTable: React.FC<Props> = ({
  prompts,
  selectedIds,
  onSelect,
  onEdit,
  onDelete,
  onTest
}) => {
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null)
  const [menuPrompt, setMenuPrompt] = React.useState<Prompt | null>(null)

  const openMenu = (event: React.MouseEvent<HTMLElement>, p: Prompt) => {
    setAnchorEl(event.currentTarget)
    setMenuPrompt(p)
  }
  const closeMenu = () => {
    setAnchorEl(null)
    setMenuPrompt(null)
  }

  const allSelected   = prompts.length > 0 && selectedIds.length === prompts.length
  const someSelected  = selectedIds.length > 0 && selectedIds.length < prompts.length

  const toggleSelectAll = () => {
    if (allSelected) onSelect([])
    else onSelect(prompts.map(p => p.id))
  }

  const toggleSelect = (id: string) => {
    if (selectedIds.includes(id)) onSelect(selectedIds.filter(i => i !== id))
    else onSelect([...selectedIds, id])
  }

  return (
    <>
      <TableContainer component={Paper} sx={{ mt: 2 }}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox
                  indeterminate={someSelected}
                  checked={allSelected}
                  onChange={toggleSelectAll}
                />
              </TableCell>
              <TableCell>Text</TableCell>
              <TableCell>Golden Answer</TableCell>
              <TableCell>Tags</TableCell>
              <TableCell align="right">Aktionen</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {prompts.map(p => {
              const checked = selectedIds.includes(p.id)
              return (
                <TableRow key={p.id} hover>
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={checked}
                      onChange={() => toggleSelect(p.id)}
                    />
                  </TableCell>
                  <TableCell>{p.text}</TableCell>
                  <TableCell>{p.golden_answer}</TableCell>
                  <TableCell>{p.tags.join(', ')}</TableCell>
                  <TableCell align="right">
                    <IconButton
                      size="small"
                      onClick={e => openMenu(e, p)}
                      aria-label="Mehr Aktionen"
                    >
                      <MoreVertIcon />
                    </IconButton>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </TableContainer>

      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={closeMenu}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <MenuItem onClick={() => { menuPrompt && onEdit(menuPrompt); closeMenu() }}>
          <EditIcon fontSize="small" sx={{ mr: 1 }} /> Edit
        </MenuItem>
        <MenuItem onClick={() => { menuPrompt && onDelete(menuPrompt.id); closeMenu() }}>
          <DeleteIcon fontSize="small" sx={{ mr: 1 }} /> Delete
        </MenuItem>
        <MenuItem onClick={() => { menuPrompt && onTest(menuPrompt.id); closeMenu() }}>
          <PlayArrowIcon fontSize="small" sx={{ mr: 1 }} /> Test
        </MenuItem>
      </Menu>
    </>
  )
}

export default PromptTable
