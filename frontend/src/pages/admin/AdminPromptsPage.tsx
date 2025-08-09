// src/pages/admin/AdminPromptsPage.tsx
import React, { useEffect, useState } from 'react'
import { Container, Stack, Button, Typography } from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import UploadIcon from '@mui/icons-material/Upload'
import { useAdminPrompt } from '../../state/AdminPromptContext'
import type { Prompt, TestParams } from '../../api/models'
import { startRun, getRunStatus, getRunResults } from '../../api/api'
import PromptTable from '../../components/PromptTable/PromptTable'
import PromptFormModal from '../../components/PromptFormModal/PromptFormModal'
import ImportDialog from '../../components/ImportDialog/ImportDialog'
import TagFilter from '../../components/TagFilter/TagFilter'
import Spinner from '../../components/ui/spinner'
import BatchTestDialog from '../../components/BatchTestDialog/BatchTestDialog'
import PromptTestModal from '../../components/PromptTestModal/PromptTestModal'

const AdminPromptsPage: React.FC = () => {
  const { state, loadPrompts, addPrompt, editPrompt, removePrompt, importFile } = useAdminPrompt()

  // Filter-Tag
  const [filterTag, setFilterTag] = useState<string | undefined>(undefined)
  // Auswahl für Batch oder Einzel
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  // Test-Parameter (werden im Dialog verändert)
  const [runParams, setRunParams] = useState<TestParams>({
    model: 'gpt-4o',
    temperature: 0.7,
    max_tokens: 1000,
    top_p: 1
  })

  // Run-Tracking
  const [runId, setRunId] = useState<string | null>(null)
  const [runStatus, setRunStatus] = useState<{
    status: string
    total: number
    completed: number
  } | null>(null)

  // Modals
  const [editOpen, setEditOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)
  const [testModal, setTestModal] = useState<{
    open: boolean
    runId: string
    promptId: string
    params: TestParams
  }>({ open: false, runId: '', promptId: '', params: runParams })

  const handleTest = async (promptId: string) => {
    // 1) Run starten
    const runId = await startRun([promptId], testModal.params)
    setTestModal({ open: true, runId, promptId, params: testModal.params })
  }

  // zu bearbeitender Prompt
  const [editing, setEditing] = useState<Prompt | undefined>(undefined)

  useEffect(() => { loadPrompts() }, [])

  // Polling, wenn ein Run aktiv ist
  useEffect(() => {
    if (!runId) return
    const iv = window.setInterval(async () => {
      const status = await getRunStatus(runId)
      setRunStatus(status)
      if (status.status === 'Done') clearInterval(iv)
    }, 1000)
    return () => window.clearInterval(iv)
  }, [runId])

  // Tag-Filter anwenden
  const filtered = filterTag
    ? state.prompts.filter(p => p.tags.includes(filterTag))
    : state.prompts

  // Einzel-Test → öffne einfach Batch-Dialog mit nur 1 Auswahl
  const handleSingleTest = (promptId: string) => {
    setSelectedIds([promptId])
    setBatchOpen(true)
  }

  return (
    <Container
      disableGutters
      maxWidth={false}
      sx={{ mt: 4, mb: 4 }}
    >
      {/* Toolbar */}
      <Stack direction="row" spacing={2} alignItems="center" mb={2}>
        <Typography variant="h4">Übersicht aller Test Prompts</Typography>
        <Button
          startIcon={<AddIcon />}
          variant="contained"
          onClick={() => { setEditing(undefined); setEditOpen(true) }}
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

      {/* Loading / Error */}
      {state.loading && <Spinner />}
      {state.error && <Typography color="error" gutterBottom>{state.error}</Typography>}

      {/* Prompt-Tabelle mit Auswahl, Bearbeiten, Löschen, Testen */}
      <PromptTable
        prompts={filtered}
        selectedIds={selectedIds}
        onSelect={setSelectedIds}
        onEdit={p => { setEditing(p); setEditOpen(true) }}
        onDelete={id => removePrompt(id)}
        onTest={handleSingleTest}
      />

      {/* Batch-Test starten */}
      <Button
        variant="contained"
        disabled={selectedIds.length === 0}
        onClick={() => setBatchOpen(true)}
        sx={{ mt: 2 }}
      >
        Batch Test starten
      </Button>

      {/* Batch-Lauf Status */}
      {runStatus && runId && (
        <Typography sx={{ mt: 2 }}>
          Lauf <strong>{runId}</strong>: {runStatus.completed} / {runStatus.total} – {runStatus.status}
        </Typography>
      )}

      {/* ——— MODALS ——— */}

      {/* Prompt anlegen / bearbeiten */}
      <PromptFormModal
        open={editOpen}
        prompt={editing}
        onClose={() => setEditOpen(false)}
        onSubmit={data => {
          if (editing) editPrompt(editing.id, data)
          else addPrompt(data)
          setEditOpen(false)
        }}
      />

      {/* Importieren */}
      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImport={file => importFile(file).then(() => setImportOpen(false))}
      />

      {/* BatchTestDialog wird auch für Single-Test verwendet */}
      {batchOpen && (
        <BatchTestDialog
          open={batchOpen}
          prompts={filtered}
          initialSelected={selectedIds}
          params={runParams}
          onParamsChange={setRunParams}
          onStart={async (ids, params) => {
            // 1) Run starten
            const id = await startRun(ids, params)
            setRunId(id)
            // 2) Wenn Einzel-Test, sofort Modal öffnen
            if (ids.length === 1) {
              setTestModal({ open: true, runId: id, promptId: ids[0], params })
            }
            setBatchOpen(false)
          }}
          onClose={() => setBatchOpen(false)}
        />
      )}

      {/* PromptTestModal */}
      {testModal.open && (
        <PromptTestModal
          open={true}
          runId={testModal.runId}
          promptId={testModal.promptId}
          params={testModal.params}
          onClose={() => setTestModal(m => ({ ...m, open: false }))}
        />
      )}
    </Container>
  )
}

export default AdminPromptsPage
