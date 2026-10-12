'use client';

import { useEffect, useRef, useState } from 'react';

import { conversations } from '@/lib/api';
import { firstNameOf } from '@/lib/format';
import { useSession } from '@/lib/session';
import { cancelRun, followRun, streamMessage, type StreamHandlers } from '@/lib/stream';
import type { ConversationDetail } from '@/lib/types';
import { useUploads } from '@/lib/useUploads';
import ChatComposer from '@/components/chat/ChatComposer';
import ChatHeader from '@/components/chat/ChatHeader';
import MessageTimeline, { type Turn } from '@/components/chat/MessageTimeline';
import SuggestedPrompts from '@/components/chat/SuggestedPrompts';
import Orb from '@/components/ui/Orb';

const newId = () => Math.random().toString(36).slice(2, 10);

/** "Good morning" before noon, "Good afternoon" until five, "Good evening" after. */
function greeting(now: Date): string {
  const hour = now.getHours();

  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';

  return 'Good evening';
}

/** Turn a saved chat into the turns the timeline draws. */
function turnsFrom(detail: ConversationDetail): Turn[] {
  return detail.messages.map((message) => ({
    id: `m${message.id}`,
    role: message.role === 'user' ? 'user' : 'planner',
    text:
      message.role === 'assistant' && message.status === 'failed' && !message.text
        ? 'This reply could not be completed.'
        : message.text,
    at: new Date(message.created_at),
    failed: message.status === 'failed',
    stopped: message.status === 'cancelled',
  }));
}

/**
 * The chat pane.
 *
 * Mounted fresh for every chat: the shell changes its key on New Chat and on picking
 * a past chat, so no state from one conversation can leak into the next.
 *
 * With `openConversationId` set, the saved messages are loaded first. If a reply in
 * that chat is still being written, the pane rejoins its run and the words carry on
 * arriving, exactly as if the person had never left.
 *
 * Leaving a chat stops listening but does not stop the run. The reply keeps being
 * written on the server, and opening the chat again picks it up.
 *
 * `onActivity` tells the shell which chat this is and that the history list should
 * refresh: once when a message starts a run, and again when the reply ends.
 */
export default function ChatWorkspace({
  userId,
  openConversationId = null,
  onActivity,
  onShowHistory,
}: {
  userId: number | null;
  openConversationId?: number | null;
  onActivity?: (conversationId: number) => void;
  onShowHistory?: () => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [step, setStep] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<number | null>(openConversationId);
  const [loading, setLoading] = useState(openConversationId !== null);
  const [loadFailed, setLoadFailed] = useState(false);

  const uploads = useUploads(userId);

  // The run writing the current reply, and whether Stop was pressed before its id arrived.
  const runId = useRef<number | null>(null);
  const stopWanted = useRef(false);

  // Aborted when the pane unmounts, so a chat that was left stops listening to its stream.
  const listening = useRef<AbortController | null>(null);

  // The latest conversation id, readable from inside a stream that started before it was known.
  const conversationIdRef = useRef(conversationId);

  const session = useSession();
  const firstName = session.status === 'signed-in' ? firstNameOf(session.user.name) : '';

  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  useEffect(() => {
    const controller = new AbortController();

    listening.current = controller;

    return () => controller.abort();
  }, []);

  // Pin to the newest turn as it grows.
  useEffect(() => {
    const element = scroller.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [turns, step]);

  /** Put the caret back in the composer when a turn finishes, so typing needs no click. */
  useEffect(() => {
    if (!busy && !loading) composer.current?.focus();
  }, [busy, loading]);

  /** The stream callbacks for one answer turn, each writing into that turn only. */
  function handlersFor(answerId: string): StreamHandlers {
    function amend(change: (turn: Turn) => Turn) {
      setTurns((current) => current.map((turn) => (turn.id === answerId ? change(turn) : turn)));
    }

    return {
      onRun: (run) => {
        setConversationId(run.conversation_id);
        onActivity?.(run.conversation_id);
        runId.current = run.run_id;
        if (stopWanted.current) void cancelRun(run.run_id);
      },
      onSnapshot: (text) => amend((turn) => ({ ...turn, text })),
      onToken: (piece) => amend((turn) => ({ ...turn, text: turn.text + piece })),
      onDone: (text) => amend((turn) => ({ ...turn, text })),
      onCancelled: (text) => amend((turn) => ({ ...turn, text: text || turn.text, stopped: true })),
      onError: (message) => amend((turn) => ({ ...turn, text: turn.text || message, failed: true })),
    };
  }

  /** Run one stream to its end, then reset the working state. A pane that was left says nothing. */
  async function listen(answerId: string, start: (handlers: StreamHandlers, signal?: AbortSignal) => Promise<void>) {
    const signal = listening.current?.signal;
    const handlers = handlersFor(answerId);

    setBusy(true);
    setStep('Thinking');

    await start(handlers, signal).catch(() => {
      if (signal?.aborted) return;

      handlers.onError('The planner could not be reached. Check that the backend is running.');
    });

    if (signal?.aborted) return;

    const finishedIn = runId.current === null ? null : conversationIdRef.current;

    runId.current = null;
    stopWanted.current = false;
    setStep(null);
    setBusy(false);

    if (finishedIn !== null) onActivity?.(finishedIn);
  }

  // Open a past chat: load its messages, then rejoin its run if a reply is still being written.
  useEffect(() => {
    if (openConversationId === null) return;

    let live = true;

    conversations
      .get(openConversationId)
      .then((detail) => {
        if (!live) return;

        const loaded = turnsFrom(detail);
        const active = detail.active_run;

        setTurns(loaded);
        setLoading(false);

        const answer = loaded.at(-1);

        if (active && answer?.role === 'planner') {
          runId.current = active.run_id;
          void listen(answer.id, (handlers, signal) => followRun(active.run_id, handlers, signal));
        }
      })
      .catch(() => {
        if (!live) return;

        setLoading(false);
        setLoadFailed(true);
      });

    return () => {
      live = false;
    };
    // Runs once per mount: the shell remounts this pane to open a different chat.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openConversationId]);

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy || loading || uploads.reading || typeof userId !== 'number') return;

    const answerId = newId();

    // Read before clearing: the chips are emptied as the message is sent, and these ids are what
    // ties the reply to the files it is about.
    const importIds = uploads.importIds;
    const attached = uploads.attachments.map((item) => item.name);

    setDraft('');
    uploads.clear();
    setTurns((current) => [
      ...current,
      { id: newId(), role: 'user', text: trimmed, at: new Date(), attached },
      { id: answerId, role: 'planner', text: '', at: new Date(), importIds },
    ]);

    await listen(answerId, (handlers, signal) => streamMessage(conversationId, trimmed, handlers, signal));
  }

  /** Stop the reply being written. If the run id has not arrived yet, stop it as soon as it does. */
  function stop() {
    stopWanted.current = true;
    if (runId.current !== null) void cancelRun(runId.current);
  }

  /**
   * Ask the same question again. The answer is a new run in the same conversation, so
   * the old reply stays on screen and the fresh one is added below it.
   */
  function regenerate(answerId: string) {
    const at = turns.findIndex((turn) => turn.id === answerId);
    const question = turns
      .slice(0, at)
      .findLast((turn) => turn.role === 'user');

    if (question) void send(question.text);
  }

  const streamingId = busy ? turns.at(-1)?.id : undefined;
  const empty = turns.length === 0 && openConversationId === null;

  const composerProps = {
    value: draft,
    onChange: setDraft,
    onSend: () => send(draft),
    onStop: stop,
    busy,
    inputRef: composer,
    attachments: uploads.attachments,
    onAttach: (files: File[]) => void uploads.add(files),
    onRemoveAttachment: uploads.remove,
    onUnlockAttachment: (key: string, password: string) => void uploads.unlock(key, password),
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ChatHeader started={!empty} onShowHistory={onShowHistory} />

      {/* min-h-0 is load-bearing: without it this flex child will not shrink below
          its content, so it never scrolls and the column grows past the viewport. */}
      <div ref={scroller} className="quiet-scroll min-h-0 flex-1 overflow-y-auto pb-4">
        {empty ? (
          <div className="flex min-h-full flex-col items-center justify-center px-4 py-8 sm:px-8">
            <Orb size={76} />

            <h2 className="mt-6 max-w-[22ch] text-center text-[22px] leading-[1.3] font-semibold tracking-[-0.015em] text-primary">
              {greeting(new Date())}{firstName ? `, ${firstName}` : ''}! How can I assist you?
            </h2>

            <div className="mt-7 w-full max-w-[560px]">
              <ChatComposer {...composerProps} variant="hero" />
            </div>

            <div className="mt-6 w-full max-w-[560px]">
              <SuggestedPrompts onPick={send} />
            </div>
          </div>
        ) : loading ? (
          <p className="mx-auto max-w-5xl px-6 pt-4 text-[12.5px] text-muted">Loading conversation…</p>
        ) : loadFailed ? (
          <p className="mx-auto max-w-5xl px-6 pt-4 text-[12.5px] text-negative">
            This conversation could not be opened. Start a new chat or try again.
          </p>
        ) : (
          <MessageTimeline
            turns={turns}
            streamingId={streamingId}
            userId={userId}
            busy={busy}
            onRegenerate={regenerate}
          />
        )}

        {step && (
          <p
            aria-live="polite"
            className="mx-auto mt-3 flex w-full max-w-5xl items-center gap-2 px-4 text-[12px] text-secondary sm:px-6"
          >
            <span className="flex gap-1" aria-hidden="true">
              <Dot delay="0ms" />
              <Dot delay="140ms" />
              <Dot delay="280ms" />
            </span>
            {step}
          </p>
        )}
      </div>

      {!empty && (
        <div className="mx-auto w-full max-w-5xl px-1 sm:px-2">
          <ChatComposer {...composerProps} />
        </div>
      )}
    </div>
  );
}

/** One cell of the working indicator. */
function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="h-1.5 w-1.5 animate-pulse rounded-full"
      style={{ background: 'var(--accent)', animationDelay: delay }}
    />
  );
}
