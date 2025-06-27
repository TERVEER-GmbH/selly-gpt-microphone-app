import { useState, useRef } from 'react';

export function MicButton() {
    const [listening, setListening] = useState(false);
    const mediaRecorder = useRef<MediaRecorder>();
    const silenceTimer = useRef<number>();

    async function startListening() {
        const stream = await navigator.mediaDevices.getUserMedia({ audio:true });
        const audioCtx = new AudioContext();
        const source = audioCtx.createMediaStreamSource(stream);
        const processor = audioCtx.createScriptProcessor(2048, 1, 1);

        source.connect(processor)
        processor.connect(audioCtx.destination)

        mediaRecorder.current = new MediaRecorder(stream);
    const chunks: BlobPart[] = [];

    mediaRecorder.current.ondataavailable = ev => chunks.push(ev.data);
    mediaRecorder.current.onstop = async () => {
      const blob = new Blob(chunks, { type: 'audio/wav' });
      await fetch('/transcribe', {
        method: 'POST',
        body: blob,
      })
      .then(res => res.json())
      .then(data => {
        console.log('Transcribed text:', data.text);
        // inject into your chat input…
      });
      setListening(false);
      processor.disconnect();
      audioCtx.close();
    };

    processor.onaudioprocess = e => {
      const input = e.inputBuffer.getChannelData(0);
      const rms = Math.sqrt(input.reduce((s, v) => s + v*v, 0) / input.length);
      if (rms < 0.01) {
        if (!silenceTimer.current) {
          silenceTimer.current = window.setTimeout(() => {
            mediaRecorder.current?.stop();
          }, 3_000);
        }
      } else {
        clearTimeout(silenceTimer.current);
        silenceTimer.current = undefined;
      }
    };

    mediaRecorder.current.start();
    setListening(true);
  }

  return (
    <button onClick={startListening} disabled={listening}>
      {listening ? 'Listening…' : '🎤 Speak'}
    </button>
  );
}
