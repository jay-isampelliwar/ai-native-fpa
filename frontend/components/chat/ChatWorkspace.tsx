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

const newId = () => Math.random().toString(36).slice(2, 10);

export default function ChatWorkspace({
  userId,
  onResetWidth,
}: {
  userId: number | null;
  onResetWidth?: () => void;
}) {
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

  const streamingId = busy ? turns.at(-1)?.id : undefined;
  const empty = turns.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ChatHeader onCollapse={onResetWidth} />

      {/* min-h-0 is load-bearing: without it this flex child will not shrink below
          its content, so it never scrolls and the column grows past the viewport. */}
      <div ref={scroller} className="quiet-scroll min-h-0 flex-1 overflow-y-auto pb-4">
        {empty ? (
          <div className="space-y-6">
            <div className="px-4 pt-2 sm:px-5">
              <h2 className="text-[21px] leading-[1.25] font-bold tracking-[-0.015em] text-primary">
                Hi {PROFILE.firstName},
                <br />
                How can I help you today?
              </h2>

              <p className="mt-2 text-[13px] leading-[1.55] text-secondary">
                Get personalised insights, plan smarter, and stay on track with your financial
                goals.
              </p>
            </div>

            <SuggestedPrompts onPick={send} />
          </div>
        ) : (
          <MessageTimeline turns={turns} streamingId={streamingId} userId={userId} />
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

      <ChatComposer
        value={draft}
        onChange={setDraft}
        onSend={() => send(draft)}
        onStop={stop}
        busy={busy}
        inputRef={composer}
        attachments={uploads.attachments}
        onAttach={(files) => void uploads.add(files)}
        onRemoveAttachment={uploads.remove}
        onUnlockAttachment={(key, password) => void uploads.unlock(key, password)}
      />
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
