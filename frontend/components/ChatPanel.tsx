'use client';

import { useEffect, useRef, useState } from 'react';

import { BlockRenderer } from '@/components/blocks';
import { useUser } from '@/components/Shell';
import { planner } from '@/lib/api';
import { streamMessage } from '@/lib/stream';
import type { Block, MessageResponse } from '@/lib/types';

/**
 * The conversation — one graph run per message, streamed, with approvals answered inline.
 *
 * Progress events drive the placeholder rather than a generic spinner. The graph already knows
 * whether it is routing, reading records or verifying a result, and saying so is the difference
 * between waiting and wondering — especially on the investigation skill, which takes several seconds.
 *
 * The conversation id is held from the first reply onwards and sent with every later message. It is
 * the graph's thread id, so it is also what makes an approval resume the exact paused run rather than
 * starting a fresh one that would re-propose against newer records.
 *
 * An approval replaces the turn that proposed it rather than appending below it. The card was a
 * question; once answered it should stop looking like one, and a live Approve button sitting above
 * the outcome invites a second click on a decision already made.
 *
 * Errors become a turn rather than a toast. A failure to answer a question about money is part of the
 * record of what was asked, and dismissing it leaves a gap the reader cannot account for.
 */

type Turn = {
  id: string;
  role: 'user' | 'planner';
  text: string;
  blocks: Block[];
  skill?: string | null;
  calculators?: string[];
  conversationId?: string;
};

const OPENERS = [
  'How much is left over this month?',
  'Why did I spend more last month?',
  'Am I on track for my house goal?',
];

const newId = () => Math.random().toString(36).slice(2, 10);

export default function ChatPanel() {
  const userId = useUser();

  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [progress, setProgress] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();

  const scroller = useRef<HTMLDivElement>(null);

  // Pin to the newest turn as it arrives.
  useEffect(() => {
    const element = scroller.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [turns, progress]);

  function record(response: MessageResponse) {
    setConversationId(response.conversation_id);

    setTurns((current) => [
      ...current,
      {
        id: newId(),
        role: 'planner',
        text: response.response,
        blocks: response.blocks,
        skill: response.skill,
        calculators: response.calculator_versions,
        conversationId: response.conversation_id,
      },
    ]);
  }

  function fail(text: string) {
    setTurns((current) => [...current, { id: newId(), role: 'planner', text, blocks: [] }]);
  }

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy) return;

    setDraft('');
    setTurns((current) => [...current, { id: newId(), role: 'user', text: trimmed, blocks: [] }]);
    setBusy(true);
    setProgress('Sending');

    await streamMessage(userId, trimmed, conversationId, {
      onProgress: (event) => setProgress(event.label),
      onDone: record,
      onError: fail,
    }).catch(() => fail('The planner could not be reached. Check that the backend is running.'));

    setProgress(null);
    setBusy(false);
  }

  async function decide(turnId: string, decision: 'approve' | 'reject') {
    const turn = turns.find((candidate) => candidate.id === turnId);
    if (!turn?.conversationId) return;

    const outcome = await planner.decide(userId, turn.conversationId, decision);

    setTurns((current) =>
      current.map((candidate) =>
        candidate.id === turnId
          ? {
              ...candidate,
              text: outcome.response,
              blocks: outcome.blocks.filter((block) => block.type !== 'approval_card'),
            }
          : candidate,
      ),
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* min-h-0 is load-bearing: without it a flex child will not shrink below its content, so this
          never scrolls and the column grows past the viewport. */}
      <div ref={scroller} className="no-scrollbar min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[760px] space-y-5 px-5 py-7">
          {turns.length === 0 && (
            <div className="pt-6">
              <h1 className="font-serif text-[30px] leading-[1.12] tracking-[-0.015em] text-[#18312f]">
                What would you like to know?
              </h1>

              <p className="mt-2.5 max-w-[46ch] text-[14px] leading-6 text-[#4d6560]">
                Every answer is built from your own records, and shows you which ones.
              </p>

              <div className="mt-6 flex flex-wrap gap-2">
                {OPENERS.map((opener) => (
                  <button
                    key={opener}
                    type="button"
                    onClick={() => send(opener)}
                    className="rounded-full border border-[#18312f]/12 bg-white/70 px-3.5 py-2 text-[12.5px] text-[#4d6560] transition hover:border-[#00947a] hover:text-[#18312f]"
                  >
                    {opener}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn) =>
            turn.role === 'user' ? (
              <div key={turn.id} className="flex justify-end">
                <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-[#183f3a] px-3.5 py-2.5 text-[14px] leading-6 text-[#f5f2e8]">
                  {turn.text}
                </p>
              </div>
            ) : (
              <div key={turn.id} className="space-y-2">
                {turn.blocks.length > 0 ? (
                  <BlockRenderer
                    blocks={turn.blocks}
                    onDecide={
                      turn.blocks.some((block) => block.type === 'approval_card')
                        ? (decision) => decide(turn.id, decision)
                        : undefined
                    }
                  />
                ) : (
                  <p className="whitespace-pre-wrap text-[14px] leading-[1.65] text-[#22423e]">
                    {turn.text}
                  </p>
                )}

                {(turn.skill || turn.calculators?.length) && (
                  <p className="text-[11px] text-[#a8b8b4]">
                    {turn.skill && <span className="font-mono">{turn.skill}</span>}
                    {turn.calculators?.length ? <span> · {turn.calculators.join(', ')}</span> : null}
                  </p>
                )}
              </div>
            ),
          )}

          {progress && (
            <div className="flex items-center gap-2 text-[12.5px] text-[#a8b8b4]">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#e7a14d]" />
              {progress}
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-[#18312f]/8 bg-white/45 px-5 py-4">
        <div className="mx-auto w-full max-w-[760px]">
          <div className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  send(draft);
                }
              }}
              rows={1}
              disabled={busy}
              placeholder={busy ? 'One moment…' : 'Ask about your surplus, a goal, or your spending'}
              className="max-h-36 min-h-[44px] flex-1 resize-none rounded-xl border border-[#18312f]/12 bg-white/90 px-3.5 py-2.5 text-[14px] leading-6 text-[#18312f] outline-none transition placeholder:text-[#a8b8b4] focus:border-[#00947a] disabled:opacity-60"
            />

            <button
              type="button"
              onClick={() => send(draft)}
              disabled={busy || !draft.trim()}
              className="h-[44px] rounded-xl bg-[#e7a14d] px-4 text-[13.5px] font-semibold text-[#18312f] transition hover:bg-[#dda044] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Send
            </button>
          </div>

          <p className="mt-2.5 text-[11px] leading-4 text-[#a8b8b4]">
            The planner reads your records and explains them. It never changes anything without asking first.
          </p>
        </div>
      </div>
    </div>
  );
}
