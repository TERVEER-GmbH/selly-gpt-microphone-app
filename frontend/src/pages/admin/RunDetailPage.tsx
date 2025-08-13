import React from 'react'
import { useParams } from 'react-router-dom'
import { Box, Container, Paper, Stack, Alert } from '@mui/material'
import { getRunStatus, getRunResults, patchRunResult, renameRun } from '../../api/api'
import type { RunStatus, TestResult, TestResultUpdate } from '../../api/models'
import ResultEditDialog from '../../components/ResultEditDialog/ResultEditDialog'
import RenameRunDialog from '../../components/admin/RenameRunDialog'

import RunHeader from '../../components/run-detail/RunHeader'
import RunKPIs from '../../components/run-detail/RunKPIs'
import ResultsToolbar from '../../components/run-detail/ResultsToolbar'
import ResultsTable from '../../components/run-detail/ResultsTable'

const POLL_MS = 1200

const RunDetailPage: React.FC = () => {
  const { runId = '' } = useParams<{ runId: string }>()
  const [status, setStatus] = React.useState<RunStatus | null>(null)
  const [results, setResults] = React.useState<TestResult[]>([])
  const [loading, setLoading] = React.useState<boolean>(true)
  const [error, setError] = React.useState<string | null>(null)

  const [editing, setEditing] = React.useState<TestResult | null>(null)
  const [saving, setSaving] = React.useState<boolean>(false)

  // Rename
  const [renameOpen, setRenameOpen] = React.useState(false)
  const [renaming, setRenaming] = React.useState(false)

  // UI state
  const [query, setQuery] = React.useState('')
  const [dense, setDense] = React.useState(false)
  const [expandSignal, setExpandSignal] = React.useState<{ action: 'expand'|'collapse'; seq: number } | undefined>(undefined)

  const loadAll = React.useCallback(async () => {
    if (!runId) return
    setError(null)
    try {
      const [st, res] = await Promise.all([getRunStatus(runId), getRunResults(runId)])
      setStatus(st)
      setResults(res)
    } catch (e: any) {
      console.error(e)
      setError('Konnte Run/Ergebnisse nicht laden.')
    } finally {
      setLoading(false)
    }
  }, [runId])

  React.useEffect(() => { loadAll() }, [loadAll])

  React.useEffect(() => {
    if (!runId) return
    if (!status || status.status === 'Done') return
    if (editing) return
    const iv = window.setInterval(async () => {
      try {
        const st = await getRunStatus(runId)
        setStatus(st)
        const res = await getRunResults(runId)
        setResults(res)
      } catch {}
    }, POLL_MS)
    return () => window.clearInterval(iv)
  }, [runId, status?.status, editing])

  const handleSaveEdit = async (patch: TestResultUpdate) => {
    if (!runId || !editing) return
    try {
      setSaving(true)
      await patchRunResult(runId, editing.id, patch)
      setResults(prev => prev.map(r => (r.id === editing.id ? ({ ...r, ...patch } as TestResult) : r)))
      setEditing(null)
    } catch (e: any) {
      console.error(e); alert('Speichern fehlgeschlagen.')
    } finally { setSaving(false) }
  }

  const handleRename = async (newName: string) => {
    if (!runId) return
    try {
      setRenaming(true)
      await renameRun(runId, newName)
      setStatus(prev => (prev ? { ...prev, name: newName } as RunStatus : prev))
      setRenameOpen(false)
    } catch (e) {
      console.error(e); alert('Umbenennen fehlgeschlagen.')
    } finally { setRenaming(false) }
  }

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return results
    return results.filter(r =>
      r.prompt_text.toLowerCase().includes(q) ||
      r.ai_response.toLowerCase().includes(q) ||
      r.golden_answer.toLowerCase().includes(q)
    )
  }, [results, query])

  return (
    <Container sx={{ py: 0 }}>
      <RunHeader
        runId={runId}
        status={status}
        onRefresh={loadAll}
        onOpenRename={() => setRenameOpen(true)}
      />

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* KPIs */}
      <RunKPIs results={results} />

      {/* Toolbar */}
      <ResultsToolbar
        query={query}
        onQuery={setQuery}
        dense={dense}
        onDense={setDense}
        onExpandAll={() => setExpandSignal({ action: 'expand', seq: Date.now() })}
        onCollapseAll={() => setExpandSignal({ action: 'collapse', seq: Date.now() })}
      />

      {/* Tabelle */}
      <Paper sx={{ p: 0 }}>
        <ResultsTable
          results={filtered}
          dense={dense}
          onEdit={setEditing}
          expandSignal={expandSignal}
        />
      </Paper>

      {/* Edit Dialog */}
      {editing && (
        <ResultEditDialog
          key={editing.id}
          open={!!editing}
          initial={editing}
          onClose={() => setEditing(null)}
          onSave={handleSaveEdit}
          saving={saving}
        />
      )}

      {/* Rename Dialog */}
      <RenameRunDialog
        open={renameOpen}
        initialName={status?.name || ''}
        onCancel={() => setRenameOpen(false)}
        onSave={handleRename}
        saving={renaming}
      />
    </Container>
  )
}

export default RunDetailPage
