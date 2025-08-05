// src/pages/admin/AdminPromptsPage.tsx
import React, { useEffect, useState } from 'react'
import { Container, Stack, Button, Typography } from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import UploadIcon from '@mui/icons-material/Upload'
import { useAdminPrompt } from '../../state/AdminPromptContext'
import type { Prompt } from '../../api/models'
import PromptTable from '../../components/PromptTable/PromptTable'
import PromptFormModal from '../../components/PromptFormModal/PromptFormModal'
import ImportDialog from '../../components/ImportDialog/ImportDialog'
import TagFilter from '../../components/TagFilter/TagFilter'
import Spinner from '../../components/ui/spinner'

const AdminPromptsPage: React.FC = () => {
  const { state, loadPrompts, addPrompt, editPrompt, removePrompt, importFile } = useAdminPrompt()
  const [filterTag, setFilterTag] = useState<string | undefined>(undefined)
  const [modalOpen, setModalOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [editing, setEditing] = useState<Prompt | undefined>(undefined)

  useEffect(() => { loadPrompts() }, [])

  const filtered = filterTag
    ? state.prompts.filter((p) => p.tags.includes(filterTag!))
    : state.prompts

  return (
    <Container sx={{ mt: 4 }}>
      <Stack direction="row" spacing={2} alignItems="center" mb={2}>
        <Button
          startIcon={<AddIcon />}
          variant="contained"
          onClick={() => { setEditing(undefined); setModalOpen(true) }}
        >
          Neuer Prompt
        </Button>
        <Button
          startIcon={<UploadIcon />}
          variant="outlined"
          onClick={() => setImportOpen(true)}
        >
          Import
        </Button>
        <TagFilter
          tags={[...new Set(state.prompts.flatMap(p => p.tags))]}
          onFilter={setFilterTag}
        />
      </Stack>

      {state.loading && <Spinner />}

      {state.error && (
        <Typography color="error">{state.error}</Typography>
      )}

      <PromptTable
        prompts={filtered}
        onEdit={(p) => { setEditing(p); setModalOpen(true) }}
        onDelete={(id) => removePrompt(id)}
      />

      <PromptFormModal
        open={modalOpen}
        prompt={editing}
        onClose={() => setModalOpen(false)}
        onSubmit={(data) => {
          if (editing) editPrompt(editing.id, data)
          else addPrompt(data)
          setModalOpen(false)
        }}
      />

      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImport={importFile}
      />
    </Container>
  )
}

export default AdminPromptsPage
