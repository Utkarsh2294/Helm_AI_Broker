import { useEffect, useRef, useState } from 'react';
import { api } from '../api';

export function useDictation({ caseId, onText, onNotice, onError }) {
  const [state, setState] = useState('idle');
  const active = useRef({ epoch: 0 }),
    callbacks = useRef({ onText, onNotice, onError });
  callbacks.current = { onText, onNotice, onError };
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  function stop(cancel = false) {
    const current = active.current;
    if (cancel) {
      current.cancelled = true;
      current.epoch += 1;
    }
    clearTimeout(current.silence);
    clearTimeout(current.limit);
    try {
      current.recognition?.stop();
    } catch {
      /* The browser may have already stopped recognition. */
    }
    if (current.recorder?.state === 'recording') current.recorder.stop();
    if (cancel) {
      current.stream?.getTracks().forEach((track) => track.stop());
      current.request?.abort();
      setState('idle');
    }
  }
  useEffect(() => () => stop(true), [caseId]); // Each recording is bound to its opening case.

  async function record(initialText, epoch) {
    let stream;
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
        throw new Error('Voice recording is not supported here. Type your question instead.');
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (active.current.epoch !== epoch) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find((type) =>
        MediaRecorder.isTypeSupported(type),
      );
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined),
        chunks = [];
      Object.assign(active.current, { stream, recorder });
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        clearTimeout(active.current.limit);
        if (active.current.epoch !== epoch || active.current.cancelled) return;
        setState('transcribing');
        const form = new FormData(),
          type = recorder.mimeType || 'audio/webm';
        form.append(
          'file',
          new Blob(chunks, { type }),
          type.includes('mp4') ? 'recording.m4a' : 'recording.webm',
        );
        if (caseId) form.append('case_id', caseId);
        const request = new AbortController();
        active.current.request = request;
        try {
          const result = await api('/assistant/transcribe', {
            method: 'POST',
            body: form,
            signal: request.signal,
          });
          if (active.current.epoch === epoch) {
            callbacks.current.onText(`${initialText} ${result.text}`.trim().slice(0, 1500));
            callbacks.current.onNotice(result.notice);
          }
        } catch (error) {
          if (error.name !== 'AbortError' && active.current.epoch === epoch)
            callbacks.current.onError(error.message);
        } finally {
          if (active.current.epoch === epoch) setState('idle');
        }
      };
      recorder.onerror = () => {
        if (active.current.epoch !== epoch) return;
        callbacks.current.onError('The recording could not be completed. Please try again.');
        stop(true);
      };
      recorder.start();
      setState('recording');
      active.current.limit = setTimeout(() => stop(), 60000);
      callbacks.current.onNotice(
        'Recording for local transcription, up to 60 seconds. Stop when you have finished; review the transcript before sending.',
      );
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop());
      if (active.current.epoch === epoch) {
        setState('idle');
        callbacks.current.onError(
          error.name === 'NotAllowedError'
            ? 'Microphone permission was denied. You can type instead.'
            : error.message,
        );
      }
    }
  }
  function start(initialText) {
    if (state !== 'idle') {
      if (state !== 'transcribing') stop();
      return;
    }
    const epoch = active.current.epoch + 1;
    active.current = { epoch, cancelled: false };
    if (!Recognition) {
      record(initialText, epoch);
      return;
    }
    const engine = new Recognition();
    active.current.recognition = engine;
    engine.lang = 'en-GB';
    engine.interimResults = true;
    engine.continuous = true;
    engine.onresult = (event) => {
      if (active.current.epoch !== epoch) return;
      const words = Array.from(event.results)
        .map((result) => result[0].transcript)
        .join(' ');
      callbacks.current.onText(`${initialText} ${words}`.trim().slice(0, 1500));
      clearTimeout(active.current.silence);
      active.current.silence = setTimeout(() => stop(), 2500);
    };
    engine.onend = () => {
      if (active.current.epoch === epoch && !active.current.fallback) {
        clearTimeout(active.current.silence);
        clearTimeout(active.current.limit);
        setState('idle');
      }
    };
    engine.onerror = (event) => {
      if (active.current.epoch !== epoch || active.current.cancelled || active.current.fallback)
        return;
      if (['not-allowed', 'audio-capture', 'no-speech', 'aborted'].includes(event.error)) {
        stop(true);
        callbacks.current.onError(
          'Speech was unavailable or microphone permission was denied. Type your question or try again.',
        );
        return;
      }
      active.current.fallback = true;
      clearTimeout(active.current.silence);
      clearTimeout(active.current.limit);
      engine.abort();
      record(initialText, epoch);
    };
    try {
      engine.start();
      setState('listening');
      active.current.limit = setTimeout(() => stop(), 60000);
      active.current.silence = setTimeout(() => stop(), 2500);
    } catch {
      active.current.fallback = true;
      record(initialText, epoch);
    }
  }
  return {
    state,
    start,
    stop,
    available: Boolean(
      Recognition || (navigator.mediaDevices?.getUserMedia && window.MediaRecorder),
    ),
  };
}

export function useReadAloud() {
  const [state, setState] = useState({ id: null, status: 'idle', progress: 0 }),
    [rate, setRate] = useState(1);
  const current = useRef(null);
  function stop() {
    window.speechSynthesis?.cancel();
    current.current = null;
    setState({ id: null, status: 'idle', progress: 0 });
  }
  useEffect(() => () => window.speechSynthesis?.cancel(), []);
  function speak(text, id, speed = rate, offset = 0) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.slice(offset));
    utterance.lang = 'en-GB';
    utterance.rate = speed;
    const voice = window.speechSynthesis.getVoices().find((item) => item.lang === 'en-GB');
    if (voice) utterance.voice = voice;
    current.current = { text, id, offset, position: offset, utterance };
    utterance.onboundary = (event) => {
      if (current.current?.utterance === utterance) {
        current.current.position = offset + event.charIndex;
        setState({ id, status: 'speaking', progress: (offset + event.charIndex) / text.length });
      }
    };
    utterance.onend = () => {
      if (current.current?.utterance === utterance) {
        current.current = null;
        setState({ id: null, status: 'idle', progress: 0 });
      }
    };
    utterance.onerror = utterance.onend;
    setState({ id, status: 'speaking', progress: offset / text.length });
    window.speechSynthesis.speak(utterance);
  }
  function pause() {
    window.speechSynthesis.pause();
    setState((value) => ({ ...value, status: 'paused' }));
  }
  function resume() {
    window.speechSynthesis.resume();
    setState((value) => ({ ...value, status: 'speaking' }));
  }
  function changeRate(value) {
    setRate(value);
    if (current.current) {
      const { text, id, position } = current.current;
      speak(text, id, value, position);
    }
  }
  return {
    ...state,
    rate,
    speak,
    pause,
    resume,
    stop,
    changeRate,
    available: Boolean(window.speechSynthesis),
  };
}
