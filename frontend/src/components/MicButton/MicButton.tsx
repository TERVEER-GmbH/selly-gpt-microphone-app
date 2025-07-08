import { useState, useRef, useEffect } from 'react'
import MicIcon from '../../assets/MicrophoneIcon.svg'
import CheckIcon from '../../assets/Checkmark Icon.svg'
import CrossIcon from '../../assets/Cross Mark Icon.svg'

export interface MicButtonProps {
  onTranscript: (text: string, append?: boolean) => void
}

export function MicButton({ onTranscript }: MicButtonProps) {
  const [listening, setListening] = useState(false)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<BlobPart[]>([])
  const sendOnStop = useRef(false)

  // Cleanup on unmount or when listening state changes
  useEffect(() => {
    return () => {
      if (listening) {
        cancelListening()
      }
    }
  }, [listening])

  async function startListening() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      const recorder = new MediaRecorder(stream)
      mediaRecorder.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (ev) => chunksRef.current.push(ev.data)
      recorder.onstop = async () => {
        // Stop and release media tracks
        streamRef.current?.getTracks().forEach(track => track.stop())
        setListening(false)

        if (sendOnStop.current) {
          const blob = new Blob(chunksRef.current, { type: 'audio/webm;codecs=opus' })
          try {
            const res = await fetch('/transcribe', { method: 'POST', body: blob })
            const data = await res.json()
            onTranscript(data.text, true)
          } catch (e) {
            console.error('❌ Mic: error sending blob', e)
          }
        }
      }

      recorder.start()
      setListening(true)
    } catch (err) {
      console.error('❌ Could not access microphone:', err)
      alert('Please allow microphone access.')
    }
  }

  function confirmListening() {
    sendOnStop.current = true
    if (mediaRecorder.current && mediaRecorder.current.state === 'recording') {
      mediaRecorder.current.stop()
    }
  }

  function cancelListening() {
    sendOnStop.current = false
    if (mediaRecorder.current && mediaRecorder.current.state === 'recording') {
      mediaRecorder.current.stop()
    }
    streamRef.current?.getTracks().forEach(track => track.stop())
    setListening(false)
  }

  function handleClick() {
    if (!listening) {
      startListening()
    }
  }

  return (
    <div style={{ marginLeft: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
      { !listening ? (
        <button
          onClick={handleClick}
          style={{
            cursor: 'pointer',
            background: 'none',
            border: 'none',
            padding: '0 6px',
            display: 'flex',
            alignItems: 'center',
            height: '100%'
          }}
          aria-label="Start Recording"
        >
          <img src={MicIcon} alt="MicIcon" style={{ width: 24, height: 24 }} />
        </button>
      ) : (
        <>
          <button onClick={confirmListening} aria-label="Confirm Recording" style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}>
            <img src={CheckIcon} alt="ConfirmIcon" style={{ width: 24, height: 24 }} />
          </button>
          <button onClick={cancelListening} aria-label="Cancel Recording" style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}>
            <img src={CrossIcon} alt="CancelIcon" style={{ width: 24, height: 24 }} />
          </button>
          <span style={{ fontWeight: 'bold', color: 'red' }}>Listening...</span>
        </>
      ) }
    </div>
  )
}
