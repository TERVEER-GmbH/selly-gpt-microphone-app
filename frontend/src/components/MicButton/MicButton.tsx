import { useState, useRef, useEffect } from 'react'
import MicIcon from '../../assets/MicrophoneIcon.svg'
import CheckIcon from '../../assets/Checkmark Icon.svg'
import CrossIcon from '../../assets/Cross Mark Icon.svg'

export interface MicButtonProps {
  onTranscript: (text: string, append?: boolean) => void
}

export function MicButton({ onTranscript }: MicButtonProps) {
  const [listening, setListening] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<BlobPart[]>([])
  const sendOnStop = useRef(false)
  const timerIdRef = useRef<number | null>(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => stopAll()
  }, [])

  // Timer effect
  useEffect(() => {
    if (listening) {
      setElapsed(0)
      timerIdRef.current = window.setInterval(() => setElapsed(sec => sec + 1), 1000)
    }
    return () => {
      if (timerIdRef.current) {
        clearInterval(timerIdRef.current)
        timerIdRef.current = null
      }
    }
  }, [listening])

  function startListening() {
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      streamRef.current = stream

      const recorder = new MediaRecorder(stream)
      mediaRecorder.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = ev => chunksRef.current.push(ev.data)
      recorder.onstop = async () => {
        stopAll()
        if (sendOnStop.current) {
          const blob = new Blob(chunksRef.current, { type: 'audio/webm;codecs=opus' })
          setTranscribing(true)
          try {
            const res = await fetch('/transcribe', { method: 'POST', body: blob })
            const data = await res.json()
            onTranscript(data.text, true)
          } catch (e) {
            console.error('❌ Mic: error sending blob', e)
          } finally {
            setTranscribing(false)
          }
        }
      }

      recorder.start()
      setListening(true)
    }).catch(err => {
      console.error('❌ Mic access error', err)
      alert('Please allow microphone access.')
    })
  }

  function confirmListening() {
    sendOnStop.current = true
    mediaRecorder.current?.stop()
  }

  function cancelListening() {
    sendOnStop.current = false
    mediaRecorder.current?.stop()
    stopAll()
  }

  function stopAll() {
    setListening(false)
    setTranscribing(false)
    streamRef.current?.getTracks().forEach(t => t.stop())
    if (timerIdRef.current) {
      clearInterval(timerIdRef.current)
      timerIdRef.current = null
    }
  }

  function formatTime(sec: number) {
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {!listening && !transcribing && (
        <button
          onClick={startListening}
          aria-label="Start Recording"
          style={{ background: 'none', border: 'none', cursor: 'pointer' }}
        >
          <img src={MicIcon} alt="Start" width={24} height={24} />
        </button>
      )}

      {listening && !transcribing && (
        <>
          <button
            onClick={cancelListening}
            aria-label="Cancel Recording"
            style={{ background: 'none', border: 'none', cursor: 'pointer' }}
          >
            <img src={CrossIcon} alt="Cancel" width={24} height={24} />
          </button>
          <span style={{ fontFamily: 'monospace', fontSize: 14 }}>{formatTime(elapsed)}</span>
          <button
            onClick={confirmListening}
            aria-label="Confirm Recording"
            style={{ background: 'none', border: 'none', cursor: 'pointer' }}
          >
            <img src={CheckIcon} alt="Confirm" width={24} height={24} />
          </button>
        </>
      )}

      {transcribing && (
        <span style={{ fontStyle: 'italic', color: '#555' }}>Transcribing...</span>
      )}
    </div>
  )
}
