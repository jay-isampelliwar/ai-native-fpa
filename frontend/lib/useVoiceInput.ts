'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { voice } from '@/lib/api';

/**
 * The chat mic: record the person's voice and show their words while they speak.
 *
 * Two recorders share one microphone. The short one restarts every few seconds and each piece
 * is turned into text at once, so words reach the box while the person is still talking. The
 * long one keeps the whole clip, and when recording stops that clip is turned into text once
 * more and replaces the live words, because the model hears whole sentences better than pieces.
 *
 * A piece with no voice in it is never sent. That saves the cost of silence, and a speech model
 * given silence tends to invent a word or two.
 *
 * Recording stops when the person taps the mic again, after ten quiet seconds, or after one
 * minute. The audio is never saved; only the text comes back.
 */

export type VoiceState = 'idle' | 'starting' | 'listening' | 'finishing';

const PIECE_MS = 2500;
const QUIET_STOP_MS = 10_000;
const LONGEST_MS = 60_000;
const CHECK_MS = 100;
const VOICE_LEVEL = 0.02;

const FORMATS = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];

interface Session {
  stream: MediaStream;
  audio: AudioContext;
  format: string;
  whole: MediaRecorder;
  wholeChunks: Blob[];
  piece: MediaRecorder | null;
  pieceVoiced: boolean;
  pieceCount: number;
  pieces: string[];
  heardVoice: boolean;
  startedAt: number;
  lastVoiceAt: number;
  timer: ReturnType<typeof setInterval>;
  pieceTimer: ReturnType<typeof setTimeout> | null;
  done: boolean;
}

/** The first audio format this browser can record, or an empty string to let it choose. */
function recordFormat(): string {
  return FORMATS.find((format) => MediaRecorder.isTypeSupported(format)) ?? '';
}

/** A plain-words reason why the mic could not start. */
function startError(error: unknown): string {
  const name = error instanceof DOMException ? error.name : '';

  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'The mic is blocked. Allow the microphone for this site in your browser settings, then try again.';
  }

  if (name === 'NotFoundError') return 'No microphone was found. Connect one and try again.';

  if (name === 'NotReadableError') return 'The microphone is busy in another app. Close it and try again.';

  return 'The mic could not start. Please try again.';
}

/** Record one short piece, hand it over if it had voice in it, then start the next while still listening. */
function recordPieces(current: Session, onPiece: (index: number, blob: Blob) => void): void {
  if (current.done) return;

  const recorder = new MediaRecorder(current.stream, current.format ? { mimeType: current.format } : undefined);
  const chunks: Blob[] = [];
  const index = current.pieceCount;

  current.pieceCount += 1;
  current.pieceVoiced = false;
  current.piece = recorder;

  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };

  recorder.onstop = () => {
    if (current.pieceVoiced && chunks.length > 0 && !current.done) {
      onPiece(index, new Blob(chunks, { type: recorder.mimeType || current.format }));
    }

    recordPieces(current, onPiece);
  };

  recorder.start();

  current.pieceTimer = setTimeout(() => {
    if (recorder.state === 'recording') recorder.stop();
  }, PIECE_MS);
}

export function useVoiceInput(onText: (text: string, final: boolean) => void) {
  const [state, setState] = useState<VoiceState>('idle');
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const session = useRef<Session | null>(null);
  const report = useRef(onText);

  useEffect(() => {
    report.current = onText;
  }, [onText]);

  const supported =
    typeof window !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof MediaRecorder !== 'undefined';

  /** Let go of the microphone and the audio graph. */
  const release = useCallback((current: Session) => {
    clearInterval(current.timer);
    if (current.pieceTimer) clearTimeout(current.pieceTimer);
    current.stream.getTracks().forEach((track) => track.stop());
    void current.audio.close().catch(() => undefined);
  }, []);

  /** Send one short piece and show every piece heard so far, in order. */
  const sendPiece = useCallback(async (current: Session, index: number, blob: Blob) => {
    try {
      const { text } = await voice.transcribe(blob);

      if (current.done || !text) return;

      current.pieces[index] = text;
      report.current(current.pieces.filter(Boolean).join(' '), false);
    } catch {
      // A lost piece only leaves a gap in the live words; the whole clip is read again at the end.
    }
  }, []);

  /** Record pieces one after another, sending each one that had voice in it. */
  const startPiece = useCallback(
    (current: Session) => recordPieces(current, (index, blob) => void sendPiece(current, index, blob)),
    [sendPiece],
  );

  /** Stop recording and read the whole clip once more for the final words. */
  const stop = useCallback(() => {
    const current = session.current;

    if (!current || current.done) return;

    current.done = true;
    setState('finishing');
    setLevel(0);

    if (current.pieceTimer) clearTimeout(current.pieceTimer);
    if (current.piece?.state === 'recording') current.piece.stop();

    current.whole.onstop = async () => {
      release(current);

      const live = current.pieces.filter(Boolean).join(' ');

      if (current.heardVoice && current.wholeChunks.length > 0) {
        try {
          const blob = new Blob(current.wholeChunks, { type: current.whole.mimeType || current.format });
          const { text } = await voice.transcribe(blob);

          report.current(text || live, true);
        } catch {
          report.current(live, true);
          setError(live ? 'Could not check the last words. Please read the text before sending.' : 'Could not turn your voice into text. Please try again.');
        }
      } else {
        report.current(live, true);
      }

      session.current = null;
      setState('idle');
    };

    if (current.whole.state === 'recording') {
      current.whole.stop();
    } else {
      void current.whole.onstop?.(new Event('stop'));
    }
  }, [release]);

  /** Ask for the mic, then start both recorders and the quiet and time-limit checks. */
  const start = useCallback(async () => {
    if (session.current || state !== 'idle') return;

    setError(null);

    if (!supported) {
      setError('This browser cannot record audio. Please type your message.');
      return;
    }

    setState('starting');

    let stream: MediaStream;

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (problem) {
      setError(startError(problem));
      setState('idle');
      return;
    }

    const format = recordFormat();
    const audio = new AudioContext();
    const analyser = audio.createAnalyser();
    const samples = new Float32Array(analyser.fftSize);

    audio.createMediaStreamSource(stream).connect(analyser);

    const whole = new MediaRecorder(stream, format ? { mimeType: format } : undefined);
    const now = Date.now();

    const current: Session = {
      stream,
      audio,
      format,
      whole,
      wholeChunks: [],
      piece: null,
      pieceVoiced: false,
      pieceCount: 0,
      pieces: [],
      heardVoice: false,
      startedAt: now,
      lastVoiceAt: now,
      timer: setInterval(() => {
        analyser.getFloatTimeDomainData(samples);

        let sum = 0;
        for (const sample of samples) sum += sample * sample;
        const loudness = Math.sqrt(sum / samples.length);
        const at = Date.now();

        if (loudness > VOICE_LEVEL) {
          current.lastVoiceAt = at;
          current.pieceVoiced = true;
          current.heardVoice = true;
        }

        setLevel(Math.min(loudness / (VOICE_LEVEL * 6), 1));
        setSeconds(Math.floor((at - current.startedAt) / 1000));

        if (at - current.lastVoiceAt >= QUIET_STOP_MS || at - current.startedAt >= LONGEST_MS) stop();
      }, CHECK_MS),
      pieceTimer: null,
      done: false,
    };

    whole.ondataavailable = (event) => {
      if (event.data.size > 0) current.wholeChunks.push(event.data);
    };

    session.current = current;
    whole.start();
    startPiece(current);

    setSeconds(0);
    setState('listening');
  }, [state, supported, startPiece, stop]);

  /** Tap once to start, tap again to stop. */
  const toggle = useCallback(() => {
    if (state === 'listening') stop();
    else if (state === 'idle') void start();
  }, [state, start, stop]);

  useEffect(
    () => () => {
      const current = session.current;

      if (!current) return;

      current.done = true;
      if (current.whole.state === 'recording') current.whole.stop();
      if (current.piece?.state === 'recording') current.piece.stop();
      release(current);
    },
    [release],
  );

  return {
    state,
    seconds,
    level,
    error,
    supported,
    toggle,
    stop,
    clearError: () => setError(null),
    limitSeconds: LONGEST_MS / 1000,
  };
}
