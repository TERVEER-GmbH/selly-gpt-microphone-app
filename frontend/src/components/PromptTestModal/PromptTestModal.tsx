// src/components/PromptTestModal/PromptTestModal.tsx
import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  Typography,
  Divider
} from '@mui/material';
import type { TestResult, TestParams } from '../../api/models';
import { getRunStatus, getRunResults } from '../../api/api';

interface PromptTestModalProps {
  open: boolean;
  runId: string;
  promptId: string;
  params: TestParams;
  onClose: () => void;
}

const PromptTestModal: React.FC<PromptTestModalProps> = ({
  open,
  runId,
  promptId,
  params,
  onClose
}) => {
  const [result, setResult] = useState<TestResult | null>(null);

  useEffect(() => {
    if (!open) return;

    // Polling-Loop starten
    const iv: number = window.setInterval(async () => {
      try {
        const status = await getRunStatus(runId);
        if (status.status === 'Done') {
          window.clearInterval(iv);
          // Ergebnisse laden
          const results: TestResult[] = await getRunResults(runId);
          // das eine Result-Objekt heraussuchen
          const single = results.find((r: TestResult) => r.prompt_id === promptId) ?? null;
          setResult(single);
        }
      } catch (e) {
        console.error('Fehler beim Polling des Run-Status:', e);
        window.clearInterval(iv);
      }
    }, 500);

    // Cleanup bei Unmount oder Close
    return () => window.clearInterval(iv);
  }, [open, runId, promptId, params]);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Prompt testen</DialogTitle>
      <DialogContent>
        {!result && (
          <Typography component="p">Teste…</Typography>
        )}
        {result && (
          <>
            <Typography variant="subtitle1" component="div">
              Prompt:
            </Typography>
            <Typography component="p">
              {result.prompt_text}
            </Typography>

            <Divider sx={{ my: 2 }} />

            <Typography variant="subtitle1" component="div">
              AI-Response:
            </Typography>
            <Typography component="p">
              {result.ai_response}
            </Typography>

            <Divider sx={{ my: 2 }} />

            <Typography variant="subtitle1" component="div">
              Golden Answer:
            </Typography>
            <Typography component="p">
              {result.golden_answer}
            </Typography>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default PromptTestModal;
