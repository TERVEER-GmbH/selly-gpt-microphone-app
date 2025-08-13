// src/pages/admin/AdminPromptsPage.tsx
import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  Container,
  Stack,
  Button,
  Typography,
  Chip,
  TextField,
  Paper,
  Snackbar,
  Alert as MuiAlert,
  FormControlLabel,
  Switch,
  Box
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
  import UploadIcon from '@mui/icons-material/Upload'
import { useAdminPrompt } from '../../state/AdminPromptContext'
import type { Prompt, TestParams } from '../../api/models'
import { startRun, getRunStatus } from '../../api/api'
import PromptTable from '../../components/PromptTable/PromptTable'
import PromptFormModal from '../../components/PromptFormModal/PromptFormModal'
import ImportDialog from '../../components/ImportDialog/ImportDialog'
import Spinner from '../../components/ui/spinner'
import BatchTestDialog from '../../components/BatchTestDialog/BatchTestDialog'
import PromptTestModal from '../../components/PromptTestModal/PromptTestModal'

/** Lokale Storage Keys für Persistenz */
const LS_Q = 'adminPrompts.search'
const LS_TAGS = 'adminPrompts.tags'
const LS_DENSE = 'adminPrompts.dense'

/** Prüft, ob der aktuelle Event-Target editierbar ist (Inputs, Textareas, contenteditable, MUI Autocomplete/TextField). */
function isEditableTarget(el: EventTarget | null): boolean {
  const n = el as HTMLElement | null
  if (!n) return false
  if (n.isContentEditable) return true
  const tag = n.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (n.closest?.('[role="textbox"],[role="combobox"]')) return true
  return false
}

const AdminPromptsPage: React.FC = () => {
  const { state, loadPrompts, addPrompt, editPrompt, removePrompt, importFile } = useAdminPrompt()

  // ---- Filter/ Suche / Dichte ----
  const [q, setQ] = useState<string>(() => localStorage.getItem(LS_Q) || '')
  const allTags = useMemo(() => [...new Set(state.prompts.flatMap(p => p.tags))], [state.prompts])
  const [activeTags, setActiveTags] = useState<string[]>(
    () => {
      try { return JSON.parse(localStorage.getItem(LS_TAGS) || '[]') } catch { return [] }
    }
  )
  const [dense, setDense] = useState<boolean>(() => localStorage.getItem(LS_DENSE) === '1')
  const searchRef = useRef<HTMLInputElement | null>(null)

  // ---- Auswahl & Batch/Test ----
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [runParams, setRunParams] = useState<TestParams>({
    model: 'gpt-4o',
    temperature: 0.7,
    max_tokens: 1000,
    top_p: 1
  })

  // ---- Run-Tracking für Status-Text ----
  const [runId, setRunId] = useState<string | null>(null)
  const [runStatus, setRunStatus] = useState<{
    status: string
    total: number
    completed: number
  } | null>(null)

  // ---- Modals ----
  const [editOpen, setEditOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)
  const [testModal, setTestModal] = useState<{
    open: boolean
    runId: string
    promptId: string
    params: TestParams
  }>({ open: false, runId: '', promptId: '', params: runParams })
  const [editing, setEditing] = useState<Prompt | undefined>(undefined)

  // ---- Snackbars ----
  const [snack, setSnack] = useState<{ open: boolean; msg: string; color: 'success' | 'error' | 'info' }>({
    open: false, msg: '', color: 'success'
  })
  const openSnack = (msg: string, color: 'success' | 'error' | 'info' = 'success') =>
    setSnack({ open: true, msg, color })

  // ====== Effects ======
  useEffect(() => { loadPrompts() }, []) // initial laden

  // Persistenz
  useEffect(() => { localStorage.setItem(LS_Q, q) }, [q])
  useEffect(() => { localStorage.setItem(LS_TAGS, JSON.stringify(activeTags)) }, [activeTags])
  useEffect(() => { localStorage.setItem(LS_DENSE, dense ? '1' : '0') }, [dense])

  // Polling Run Status
  useEffect(() => {
    if (!runId) return
    const iv = window.setInterval(async () => {
      try {
        const status = await getRunStatus(runId)
        setRunStatus(status)
        if (status.status === 'Done') clearInterval(iv)
      } catch {
        /* ignore */
      }
    }, 1000)
    return () => window.clearInterval(iv)
  }, [runId])

  // ==== Global Shortcuts (nur wenn kein Dialog offen & nicht in Inputs tippen) ====
  const anyDialogOpen = editOpen || importOpen || batchOpen || testModal.open
  const shortcutsEnabled = !anyDialogOpen

  useEffect(() => {
    if (!shortcutsEnabled) return

    const onKey = (e: KeyboardEvent) => {
      // blockiere Shortcuts, wenn der Fokus in einem editierbaren Element liegt
      if (isEditableTarget(e.target)) return

      const mod = e.metaKey || e.ctrlKey
      const key = e.key.toLowerCase()

      // Suche
      if (mod && key === 'f') {
        e.preventDefault()
        searchRef.current?.focus()
        return
      }
      // Neuer Prompt
      if (!mod && key === 'n') {
        e.preventDefault()
        setEditing(undefined)
        setEditOpen(true)
        return
      }
      // Import
      if (!mod && key === 'i') {
        e.preventDefault()
        setImportOpen(true)
        return
      }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [shortcutsEnabled])

  // ====== Daten-Filter ======
  const filtered = useMemo(() => {
    const ql = q.trim().toLowerCase()
    return state.prompts.filter(p => {
      const hitQ =
        !ql ||
        p.text.toLowerCase().includes(ql) ||
        p.golden_answer.toLowerCase().includes(ql) ||
        p.tags.some(t => t.toLowerCase().includes(ql))
      const hitTags = activeTags.length === 0 || activeTags.every(t => p.tags.includes(t))
      return hitQ && hitTags
    })
  }, [state.prompts, q, activeTags])

  // Einzel-Test → nutze den Batch-Dialog nur mit 1 Auswahl
  const handleSingleTest = (promptId: string) => {
    setSelectedIds([promptId])
    setBatchOpen(true)
  }

  return (
    <Container disableGutters maxWidth={false} sx={{ mt: 4, mb: 4 }}>
      {/* Toolbar */}
      <Stack spacing={2}>

        {/* Top-Row: Titel + Primäraktionen (inkl. Batch-Start) */}
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
          <Typography variant="h4">Übersicht aller Test Prompts</Typography>
          <Stack direction="row" spacing={1}>
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
            <Button
              variant="contained"
              color="primary"
              disabled={selectedIds.length === 0}
              onClick={() => setBatchOpen(true)}
            >
              Batch Test starten
            </Button>
          </Stack>
        </Stack>

        {/* Search / Chips / Dichte */}
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ xs: 'stretch', md: 'center' }}>
            <TextField
              inputRef={searchRef}
              size="small"
              label="Suchen (Text / Golden / Tag)…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              sx={{ minWidth: 260 }}
            />

            <Box sx={{ flexGrow: 1 }} />

            {/* Kompakt-Schalter */}
            <FormControlLabel
              control={<Switch size="small" checked={dense} onChange={(_, v) => setDense(v)} />}
              label="Kompakt"
              sx={{ mr: 1 }}
            />
          </Stack>

          {/* Tag-Chips Zeile */}
          <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap' }}>
            {allTags.map(t => {
              const on = activeTags.includes(t)
              return (
                <Chip
                  key={t}
                  size="small"
                  label={t}
                  variant={on ? 'filled' : 'outlined'}
                  color={on ? 'primary' : 'default'}
                  onClick={() =>
                    setActiveTags(on ? activeTags.filter(x => x !== t) : [...activeTags, t])
                  }
                />
              )
            })}
          </Stack>
        </Paper>

        {/* KPI-Chips */}
        <Stack direction="row" spacing={1}>
          <Chip size="small" label={`Prompts: ${filtered.length}`} />
          <Chip size="small" color="primary" label={`Ausgewählt: ${selectedIds.length}`} />
          <Chip size="small" label={`Tags: ${new Set(state.prompts.flatMap(p => p.tags)).size}`} />
        </Stack>
      </Stack>

      {/* Loading / Error */}
      {state.loading && <Spinner />}
      {state.error && <Typography color="error" gutterBottom>{state.error}</Typography>}

      {/* Empty State */}
      {!state.loading && filtered.length === 0 && (
        <Paper sx={{ p: 6, textAlign: 'center', mt: 2 }}>
          <Typography variant="h6" gutterBottom>Keine Prompts gefunden</Typography>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            Passen Sie die Filter an – oder legen Sie den ersten Prompt an.
          </Typography>
          <Stack direction="row" justifyContent="center" spacing={1} sx={{ mt: 1 }}>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => { setEditing(undefined); setEditOpen(true) }}
            >
              Neuer Prompt
            </Button>
            <Button
              variant="outlined"
              startIcon={<UploadIcon />}
              onClick={() => setImportOpen(true)}
            >
              Import
            </Button>
          </Stack>
        </Paper>
      )}

      {/* Tabelle in Dichte-Wrapper */}
      {filtered.length > 0 && (
        <Box
          sx={{
            mt: 2,
            '& .MuiTableCell-root': { py: dense ? 0.5 : 1.5 },
            '& .MuiTableRow-root': { height: 'auto' }
          }}
        >
          <PromptTable
            prompts={filtered}
            selectedIds={selectedIds}
            onSelect={setSelectedIds}
            onEdit={p => { setEditing(p); setEditOpen(true) }}
            onDelete={id => removePrompt(id)}
            onTest={handleSingleTest}
          />
        </Box>
      )}

      {/* Batch-Lauf Status */}
      {runStatus && runId && (
        <Typography sx={{ mt: 2 }}>
          Lauf <strong>{runId}</strong>: {runStatus.completed} / {runStatus.total} – {runStatus.status}
        </Typography>
      )}

      {/* Sticky Bulk-Bar, nur wenn Auswahl vorhanden */}
      {selectedIds.length > 0 && (
        <Paper
          elevation={3}
          sx={{
            position: 'sticky',
            bottom: 16,
            mt: 3,
            p: 1.5,
            borderRadius: 2,
            display: 'flex',
            alignItems: 'center',
            gap: 1
          }}
        >
          <Typography variant="body2" sx={{ mr: 1 }}>
            {selectedIds.length} ausgewählt
          </Typography>
          <Button size="small" variant="contained" onClick={() => setBatchOpen(true)}>
            Batch Test starten
          </Button>
          <Button
            size="small"
            onClick={() => openSnack('Feature ist im Backlog)', 'info')}
          >
            Exportieren
          </Button>
          <Button
            size="small"
            color="error"
            onClick={() => {
              selectedIds.forEach(id => removePrompt(id))
              setSelectedIds([])
              openSnack('Ausgewählte Prompts gelöscht', 'success')
            }}
          >
            Löschen
          </Button>
          <Box sx={{ flexGrow: 1 }} />
          <Button size="small" onClick={() => setSelectedIds([])}>Auswahl leeren</Button>
        </Paper>
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
          openSnack(editing ? 'Prompt aktualisiert' : 'Prompt erstellt', 'success')
        }}
      />

      {/* Importieren */}
      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImport={async (file) => {
          try {
            const res: any = await importFile(file) // kann void oder { created, errors } liefern
            const createdCount = Array.isArray(res?.created) ? res.created.length : undefined
            const errCount     = Array.isArray(res?.errors)  ? res.errors.length  : undefined

            if (createdCount != null || errCount != null) {
              openSnack(
                `Importiert: ${createdCount ?? '?'} • Fehler: ${errCount ?? 0}`,
                errCount ? 'info' : 'success'
              )
            } else {
              openSnack('Import abgeschlossen', 'success')
            }
          } catch (e) {
            console.error(e)
            openSnack('Import fehlgeschlagen', 'error')
          } finally {
            setImportOpen(false)
          }
        }}
      />

      {/* BatchTestDialog (setzt den Run-Namen intern im Dialog) */}
      {batchOpen && (
        <BatchTestDialog
          open={batchOpen}
          prompts={filtered}
          initialSelected={selectedIds}
          params={runParams}
          onParamsChange={setRunParams}
          onStart={async (ids, params, name) => {
            const id = await startRun(ids, params, name)
            setRunId(id)
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

      {/* Snackbar */}
      <Snackbar
        open={snack.open}
        autoHideDuration={3000}
        onClose={() => setSnack(s => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <MuiAlert
          elevation={3}
          variant="filled"
          severity={snack.color}
          onClose={() => setSnack(s => ({ ...s, open: false }))}
          sx={{ width: '100%' }}
        >
          {snack.msg}
        </MuiAlert>
      </Snackbar>
    </Container>
  )
}

export default AdminPromptsPage
