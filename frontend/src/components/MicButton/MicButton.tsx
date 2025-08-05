import { useState, useRef, useEffect, useCallback } from 'react'
import { Box, IconButton, Typography } from '@mui/material'
import MicIcon      from '@mui/icons-material/Mic'
import CheckIcon    from '@mui/icons-material/Check'
import CancelIcon   from '@mui/icons-material/Close'

type Status = 'idle' | 'recording' | 'transcribing'

export interface MicButtonProps {
  /**
   * Wird aufgerufen, wenn Transkription fertig ist.
   * @param text   Der erkannte Text
   * @param append Ob der Text angehängt werden soll (true) oder ersetzen (false)
   */
  onTranscript: (text: string, append: boolean) => void;
}

export function MicButton({ onTranscript }: MicButtonProps) {
  const [status, setStatus] = useState<Status>('idle')
  const [elapsed, setElapsed] = useState(0)
  const mediaRecorder = useRef<MediaRecorder>()
  const streamRef     = useRef<MediaStream>()
  const chunksRef     = useRef<BlobPart[]>([])
  const sendOnStop    = useRef(false)
  const timerId       = useRef<number>()

  // Cleanup
  const stopAll = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop())
    window.clearInterval(timerId.current!)
    setStatus('idle')
    setElapsed(0)
    chunksRef.current = []
    mediaRecorder.current = undefined
  }, [])

  // Timer Hook
  useEffect(() => {
    if (status === 'recording') {
      setElapsed(0)
      timerId.current = window.setInterval(() => setElapsed(e => e + 1), 1000)
    }
    return () => window.clearInterval(timerId.current!)
  }, [status])

  const startListening = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const recorder = new MediaRecorder(stream)
      mediaRecorder.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = e => chunksRef.current.push(e.data)
      recorder.onstop = async () => {
        if (sendOnStop.current) {
          setStatus('transcribing')
          const blob = new Blob(chunksRef.current, { type: 'audio/webm;codecs=opus' })
          try {
            const res = await fetch('/transcribe', { method: 'POST', body: blob })
            const { text } = await res.json()
            onTranscript(text, true)
          } catch {
            // z.B. setError('Transcription failed')
          }
        }
        stopAll()
      }

      recorder.start()
      setStatus('recording')
    } catch {
      // open Snackbar statt alert
    }
  }, [onTranscript, stopAll])

  const confirm = () => {
    sendOnStop.current = true
    mediaRecorder.current?.stop()
  }
  const cancel = () => {
    sendOnStop.current = false
    mediaRecorder.current?.stop()
  }

  const formatTime = (sec: number) => {
    const m = String(Math.floor(sec/60)).padStart(2,'0')
    const s = String(sec%60).padStart(2,'0')
    return `${m}:${s}`
  }

  return (
    <Box display="flex" alignItems="center">
      {status === 'idle' && (
        <IconButton onClick={startListening} aria-label="Start Recording">
          <MicIcon />
        </IconButton>
      )}
      {status === 'recording' && (
        <>
          <IconButton onClick={cancel} aria-label="Cancel">
            <CancelIcon />
          </IconButton>
          <Typography component="span" sx={{ fontFamily: 'monospace', mx: 1 }}>
            {formatTime(elapsed)}
          </Typography>
          <IconButton onClick={confirm} aria-label="Confirm">
            <CheckIcon />
          </IconButton>
        </>
      )}
      {status === 'transcribing' && (
        <Typography component="span" sx={{ fontStyle: 'italic', color: 'text.secondary' }}>
          Transcribing…
        </Typography>
      )}
    </Box>
  )
}
