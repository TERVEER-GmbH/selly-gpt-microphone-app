// frontend/src/components/MicButton.tsx
import { useState, useRef } from 'react'
import MicIcon from '../../assets/MicrophoneIcon.svg'
import RecordingIcon from '../../assets/RecordButtonIcon.svg'

export interface MicButtonProps {
  onTranscript: (text: string, append?: boolean) => void
}

export function MicButton({ onTranscript }: MicButtonProps) {
  const [listening, setListening] = useState(false)
  const mediaRecorder = useRef<MediaRecorder>()
  const silenceTimer = useRef<number>()
  const audioContextRef = useRef<AudioContext>()
  const processorRef = useRef<ScriptProcessorNode>()
  const streamRef = useRef<MediaStream>()

  async function startListening() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      const audioCtx = new AudioContext()
      audioContextRef.current = audioCtx
      const source = audioCtx.createMediaStreamSource(stream)
      const processor = audioCtx.createScriptProcessor(2048, 1, 1)
      processorRef.current = processor

      source.connect(processor)
      processor.connect(audioCtx.destination)

      const chunks: BlobPart[] = []
      const recorder = new MediaRecorder(stream)
      mediaRecorder.current = recorder

      recorder.ondataavailable = ev => chunks.push(ev.data)
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm;codecs=opus' })
        try {
          const res = await fetch('/transcribe', { method: 'POST', body: blob })
          const data = await res.json()
          onTranscript(data.text, true) // ✅ append to existing text
        } catch (e) {
          console.error("❌ Mic: error sending blob", e)
        } finally {
          setListening(false)
          processor.disconnect()
          audioCtx.close()
          stream.getTracks().forEach(track => track.stop())
        }
      }

      processor.onaudioprocess = e => {
        const input = e.inputBuffer.getChannelData(0)
        const rms = Math.sqrt(input.reduce((s, v) => s + v * v, 0) / input.length)
        if (rms < 0.02) {
          if (!silenceTimer.current) {
            silenceTimer.current = window.setTimeout(() => {
              stopListening()
            }, 1500)
          }
        } else {
          if (silenceTimer.current) {
            clearTimeout(silenceTimer.current)
            silenceTimer.current = undefined
          }
        }
      }

      recorder.start()
      setListening(true)
    } catch (err) {
      console.error("❌ Could not access microphone:", err)
      alert("Please allow microphone access.")
    }
  }

  function stopListening() {
    if (mediaRecorder.current && mediaRecorder.current.state == 'recording') {
      mediaRecorder.current.stop()
    }
    if (silenceTimer.current) {
      clearTimeout(silenceTimer.current)
      silenceTimer.current = undefined
    }
  }

  function handleClick() {
    if (listening){
      stopListening() //stop whne clicking while listening
    } else{
      startListening()
    }
  }

  return (
  <div style={{ marginLeft: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
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
      aria-labek={listening ? 'Stop Recording': 'Start Recording'}
    >
      <img
        src={listening ? RecordingIcon: MicIcon}
        alt={listening ? 'RecordingIcon': 'MicIcon'}
        style={{
          width: 24,
          height: 24,
          filter: listening ? 'drop-shadow(0 0 5px red)' : 'none',
          transition: 'filter 0.2s ease-in-out'
        }}
      />
    </button>
    {listening && <span style={{ fontWeight: 'bold', color: 'red' }}>Listening...</span>}
  </div>
)
}


