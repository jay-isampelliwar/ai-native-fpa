'use client';

import { useEffect, useRef, useState } from 'react';

import { PROFILE } from '@/lib/mock/data';
import { users } from '@/lib/api';
import { cancelRun, streamMessage } from '@/lib/stream';
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

export default function ChatWorkspace({ userId }: { userId: number | null }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [step, setStep] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<number | null>(null);

  const uploads = useUploads(userId);

  // The run writing the current reply, and whether Stop was pressed before its id arrived.
  const runId = useRef<number | null>(null);
  const stopWanted = useRef(false);

  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  // The id lives in this browser, so this is the only moment the backend can learn
  // that the person holding it exists. Idempotent, and repeated every visit.
  useEffect(() => {
    if (typeof userId !== 'number') return;

    void users.register(userId).catch(() => {
      // A backend that cannot be reached is reported by whatever is tried next,
      // which fails visibly. Failing here would only blank the pane.
    });
  }, [userId]);

  // Pin to the newest turn as it grows.
  useEffect(() => {
    const element = scroller.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [turns, step]);

  /** Put the caret back in the composer when a turn finishes, so typing needs no click. */
  useEffect(() => {
    if (!busy) composer.current?.focus();
  }, [busy]);

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy || uploads.reading || typeof userId !== 'number') return;

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
    setBusy(true);
    setStep('Thinking');

    function amend(change: (turn: Turn) => Turn) {
      setTurns((current) => current.map((turn) => (turn.id === answerId ? change(turn) : turn)));
    }

    await streamMessage(conversationId, trimmed, {
      onRun: (run) => {
        setConversationId(run.conversation_id);
        runId.current = run.run_id;
        if (stopWanted.current) void cancelRun(run.run_id);
      },
      onSnapshot: (text) => amend((turn) => ({ ...turn, text })),
      onToken: (piece) => amend((turn) => ({ ...turn, text: turn.text + piece })),
      onDone: (text) => amend((turn) => ({ ...turn, text })),
      onCancelled: (text) => amend((turn) => ({ ...turn, text: text || turn.text, stopped: true })),
      onError: (message) => amend((turn) => ({ ...turn, text: turn.text || message, failed: true })),
    }).catch(() =>
      amend((turn) => ({
        ...turn,
        text: 'The planner could not be reached. Check that the backend is running.',
        failed: true,
      })),
    );

    runId.current = null;
    stopWanted.current = false;
    setStep(null);
    setBusy(false);
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
  const empty = turns.length === 0;

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
      <ChatHeader started={!empty} />

      {/* min-h-0 is load-bearing: without it this flex child will not shrink below
          its content, so it never scrolls and the column grows past the viewport. */}
      <div ref={scroller} className="quiet-scroll min-h-0 flex-1 overflow-y-auto pb-4">
        {empty ? (
          <div className="flex min-h-full flex-col items-center justify-center px-4 py-8 sm:px-8">
            <Orb size={76} />

            <h2 className="mt-6 max-w-[22ch] text-center text-[22px] leading-[1.3] font-semibold tracking-[-0.015em] text-primary">
              {greeting(new Date())}, {PROFILE.firstName}! How can I assist you?
            </h2>

            <div className="mt-7 w-full max-w-[560px]">
              <ChatComposer {...composerProps} variant="hero" />
            </div>

            <div className="mt-6 w-full max-w-[560px]">
              <SuggestedPrompts onPick={send} />
            </div>
          </div>
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
            className="mt-3 flex items-center gap-2 px-4 text-[12px] text-secondary sm:px-5"
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

      {!empty && <ChatComposer {...composerProps} />}
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
