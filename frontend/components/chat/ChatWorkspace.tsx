'use client';

import { useEffect, useRef, useState } from 'react';

import { PROFILE } from '@/lib/mock/data';
import { users } from '@/lib/api';
import { streamMessage } from '@/lib/stream';
import ChatComposer from '@/components/chat/ChatComposer';
import ChatHeader from '@/components/chat/ChatHeader';
import MessageTimeline, { type Turn } from '@/components/chat/MessageTimeline';
import SuggestedPrompts from '@/components/chat/SuggestedPrompts';

/**
 * The left pane, and the only part of this screen wired to a real backend.
 *
 * One graph run per message, streamed. The dashboard beside it is mock data and
 * the two do not touch: this build's planner answers in prose, so there is nothing
 * structured in a reply for a card to act on, and inventing a change the model did
 * not propose would put a number on screen that nothing stands behind.
 *
 * The conversation id is held from the first reply and sent with every later
 * message. It is the graph's thread id, which is what makes the model remember
 * earlier turns. Reloading starts a new thread — the turns on screen are the only
 * copy, since the transcript endpoints do not exist.
 *
 * The answer's turn is created empty and filled as tokens arrive, then overwritten
 * with what the closing event carries. The two are identical today; the swap is
 * what keeps this correct on the day the backend checks a reply before standing
 * behind it.
 *
 * A failure becomes a turn rather than a toast. A question about money that could
 * not be answered is part of the record of what was asked, and dismissing it leaves
 * a gap the reader cannot account for.
 *
 * Identity arrives as a prop rather than being read here, and the shell remounts
 * this component when it changes. That remount is the whole of switching user:
 * turns, draft and thread id all go with it. Clearing them by hand instead would
 * mean remembering to add every new piece of state to a reset function, and the one
 * that gets forgotten leaves one person's conversation on screen under another
 * person's id.
 */

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
  const [conversationId, setConversationId] = useState<string | undefined>();

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
    if (!trimmed || busy || typeof userId !== 'number') return;

    const answerId = newId();

    setDraft('');
    setTurns((current) => [
      ...current,
      { id: newId(), role: 'user', text: trimmed, at: new Date() },
      { id: answerId, role: 'planner', text: '', at: new Date() },
    ]);
    setBusy(true);
    setStep('Thinking');

    function amend(change: (turn: Turn) => Turn) {
      setTurns((current) => current.map((turn) => (turn.id === answerId ? change(turn) : turn)));
    }

    await streamMessage(userId, trimmed, conversationId, {
      onProgress: (event) => setStep(event.label),
      onToken: (piece) => amend((turn) => ({ ...turn, text: turn.text + piece })),
      onDone: (response) => {
        setConversationId(response.conversation_id);
        amend((turn) => ({ ...turn, text: response.response }));
      },
      onError: (message) => amend((turn) => ({ ...turn, text: message, failed: true })),
    }).catch(() =>
      amend((turn) => ({
        ...turn,
        text: 'The planner could not be reached. Check that the backend is running.',
        failed: true,
      })),
    );

    setStep(null);
    setBusy(false);
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
          <MessageTimeline turns={turns} streamingId={streamingId} />
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
        busy={busy}
        inputRef={composer}
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
