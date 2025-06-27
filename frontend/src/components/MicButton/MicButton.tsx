// frontend/src/components/MicButton.tsx
import { useState, useRef } from 'react'

export interface MicButtonProps {
  onTranscript: (text: string) => void
}

export function MicButton({ onTranscript }: MicButtonProps) {
  const [listening, setListening] = useState(false)
  const mediaRecorder = useRef<MediaRecorder>()
  const silenceTimer = useRef<number>()

  async function startListening() {
    console.log("Mic: starting…")
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const audioCtx = new AudioContext()
    const source = audioCtx.createMediaStreamSource(stream)
    const processor = audioCtx.createScriptProcessor(2048, 1, 1)

    source.connect(processor)
    processor.connect(audioCtx.destination)

    mediaRecorder.current = new MediaRecorder(stream)
    const chunks: BlobPart[] = []

    mediaRecorder.current.ondataavailable = ev => chunks.push(ev.data)
    mediaRecorder.current.onstop = async () => {
      console.log("Mic: recorder stopped, sending blob…")
      const blob = new Blob(chunks, { type: 'audio/webm;codecs=opus' })
      console.log("Mic: blob size", blob.size)
      try {
        const res = await fetch('/transcribe', { method: 'POST', body: blob })
        const data = await res.json()
        console.log("Mic: got transcript", data.text)
        onTranscript(data.text)
      } catch (e) {
        console.error("Mic: error sending blob", e)
      } finally {
        setListening(false)
        processor.disconnect()
        audioCtx.close()
      }
    }

    processor.onaudioprocess = e => {
      const input = e.inputBuffer.getChannelData(0)
      const rms = Math.sqrt(input.reduce((s, v) => s + v*v, 0) / input.length)
      console.log("Mic RMS:", rms.toFixed(4))
      // adjust this threshold up or down if needed:
      if (rms < 0.02) {
        if (!silenceTimer.current) {
          console.log("Mic: silence detected, starting 3s timer")
          silenceTimer.current = window.setTimeout(() => {
            console.log("Mic: 3s of silence, stopping")
            mediaRecorder.current?.stop()
          }, 3000)
        }
      } else {
        if (silenceTimer.current) {
          console.log("Mic: sound again, clearing timer")
          clearTimeout(silenceTimer.current)
          silenceTimer.current = undefined
        }
      }
    }

    mediaRecorder.current.start()
    setListening(true)
  }

  return (
    <button onClick={startListening} disabled={listening} style={{ marginLeft: 8 }}>
      {listening ? '🎙 Listening…' : '🎤'}
    </button>
  )
}


