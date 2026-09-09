'use client';

import { useEffect, useRef, useState } from 'react';

import ImportTurn from '@/components/ImportTurn';
import { useUser } from '@/components/Shell';
import { announceRecordsChanged } from '@/lib/records';
import { streamMessage } from '@/lib/stream';

/**
 * The conversation — one graph run per message, streamed, with imports answered inline.
 *
 * A planner turn is prose. It used to carry typed blocks, the name of the skill that ran and the
 * calculator versions behind each figure, and all three are gone from here because the backend no
 * longer sends them: the agent is one model call answering in sentences. They return to this file
 * when they return to the reply, and rendering an always-empty list in the meantime is how a
 * component ends up with dead branches nobody dares delete.
 *
 * Progress is one line rather than a growing list, for the same reason. The list existed to show
 * which skill was chosen and which tool it was calling; with one node there is nothing to narrate
 * between "thinking" and the answer arriving as tokens.
 *
 * The conversation id is held from the first reply onwards and sent with every later message. It is
 * the graph's thread id, which is what makes the model remember the earlier turns. Starting a new
 * chat drops it, and that is the entire mechanism: a new thread id is a new memory.
 *
 * Past chats are not listed. The turns on screen are the only copy, so a reload starts a fresh chat -
 * the backend's transcript tables and the reads over them went with the endpoints, and pretending
 * otherwise with a "Past chats" button that always came back empty would be worse than not offering
 * it. The thread itself does survive in the checkpointer, so the id is still worth holding.
 *
 * The answer's turn is created empty and filled as the words arrive. Tokens are what the model is
 * writing; the closing event carries the text the backend stands behind, so the turn is overwritten
 * with that rather than left as whatever streamed. Today the two are identical, and the swap is what
 * keeps this correct on the day something checks the reply before it is shown.
 *
 * A file is attached in the composer rather than uploaded on a page of its own. Sending a statement is
 * the same act as asking a question — both are a person handing over something to be read — and the
 * answer to either belongs in the thread, in order, next to what was asked before it. The turn it
 * creates is live: it polls, asks for a mapping if the layout is new, and takes row decisions in place.
 *
 * A turn that changes the records tells the console rather than reloading anything itself. Committing
 * an import writes rows and the panel beside this needs to know, but this component has no business
 * knowing what that panel renders. It reports that something changed and stops there.
 *
 * Errors become a turn rather than a toast. A failure to answer a question about money is part of the
 * record of what was asked, and dismissing it leaves a gap the reader cannot account for.
 */

type Turn = {
  id: string;
  role: 'user' | 'planner' | 'import';
  text: string;
  file?: File;
};

const OPENERS = [
  'How much is left over this month?',
  'Why did I spend more last month?',
  'Am I on track for my house goal?',
];

const ACCEPTS = '.xlsx,.xlsm,.xls,.csv';

const newId = () => Math.random().toString(36).slice(2, 10);

export default function ChatPanel() {
  const userId = useUser();

  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [step, setStep] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();

  const scroller = useRef<HTMLDivElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  // Pin to the newest turn as it arrives.
  useEffect(() => {
    const element = scroller.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [turns, step]);

  function say(text: string) {
    setTurns((current) => [...current, { id: newId(), role: 'planner', text }]);
  }

  /** Drop the thread id as well as the turns — the same screen against a different memory. */
  function newSession() {
    if (busy) return;

    setTurns([]);
    setConversationId(undefined);
    setDraft('');
    setStep(null);
  }

  function attach(files: FileList | null) {
    const chosen = Array.from(files ?? []);
    if (chosen.length === 0) return;

    setTurns((current) => [
      ...current,
      ...chosen.map((file) => ({
        id: newId(),
        role: 'import' as const,
        text: file.name,
        file,
      })),
    ]);
  }

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy) return;

    const answerId = newId();

    setDraft('');
    setTurns((current) => [
      ...current,
      { id: newId(), role: 'user', text: trimmed },
      { id: answerId, role: 'planner', text: '' },
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
      onError: (message) => amend((turn) => ({ ...turn, text: message })),
    }).catch(() =>
      amend((turn) => ({
        ...turn,
        text: 'The planner could not be reached. Check that the backend is running.',
      })),
    );

    setStep(null);
    setBusy(false);
  }

  return (
    <div
      className="relative flex min-h-0 flex-1 flex-col"
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(event) => {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
        setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        attach(event.dataTransfer.files);
      }}
    >
      <div className="relative z-20 flex items-center justify-end gap-2 border-b border-[#18312f]/6 px-5 py-2">
        <button
          type="button"
          onClick={newSession}
          disabled={busy || (turns.length === 0 && !conversationId)}
          className="rounded-full border border-[#18312f]/12 bg-white/70 px-3 py-1.5 text-[11.5px] font-medium text-[#5d7470] transition hover:border-[#00947a] hover:text-[#18312f] disabled:cursor-not-allowed disabled:opacity-40"
        >
          New chat
        </button>
      </div>

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
                Ask about your money in your own words. Attach a statement and it is read here too.
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

          {turns.map((turn) => {
            if (turn.role === 'user') {
              return (
                <div key={turn.id} className="flex justify-end">
                  <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-[#183f3a] px-3.5 py-2.5 text-[14px] leading-6 text-[#f5f2e8]">
                    {turn.text}
                  </p>
                </div>
              );
            }

            if (turn.role === 'import') {
              return (
                <div key={turn.id} className="space-y-3">
                  <div className="flex justify-end">
                    <span className="flex max-w-[85%] items-center gap-2 rounded-2xl rounded-br-md bg-[#183f3a] px-3.5 py-2.5 text-[13.5px] leading-5 text-[#f5f2e8]">
                      <ClipIcon />
                      <span className="truncate">{turn.text}</span>
                    </span>
                  </div>

                  {turn.file && (
                    <ImportTurn
                      file={turn.file}
                      onCommitted={(summary) => {
                        say(summary);
                        announceRecordsChanged();
                      }}
                    />
                  )}
                </div>
              );
            }

            return (
              turn.text && (
                <p
                  key={turn.id}
                  className="whitespace-pre-wrap text-[14px] leading-[1.65] text-[#22423e]"
                >
                  {turn.text}
                </p>
              )
            );
          })}

          {step && (
            <p className="flex items-center gap-2 text-[12.5px] text-[#5d7470]">
              <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-[#e7a14d]" />
              {step}
            </p>
          )}
        </div>
      </div>

      <div className="border-t border-[#18312f]/8 bg-white/45 px-5 py-4">
        <div className="mx-auto w-full max-w-[760px]">
          <input
            ref={picker}
            type="file"
            accept={ACCEPTS}
            multiple
            className="hidden"
            onChange={(event) => {
              attach(event.target.files);
              event.target.value = ''; // so the same file can be picked twice
            }}
          />

          {/* The field is the container, not the textarea, so the clip sits inside the border with
              the caret rather than beside it as a second control competing for the same job. */}
          <div className="flex items-end gap-2 rounded-xl border border-[#18312f]/12 bg-white/90 px-2 py-1.5 transition focus-within:border-[#00947a]">
            <button
              type="button"
              onClick={() => picker.current?.click()}
              title="Attach a holdings or bank statement"
              aria-label="Attach a statement"
              className="mb-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg text-[#5d7470] transition hover:bg-[#00947a]/10 hover:text-[#00947a]"
            >
              <ClipIcon />
            </button>

            <textarea
              ref={composer}
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
              placeholder={busy ? 'One moment…' : 'Ask a question, or attach a statement'}
              className="max-h-36 min-h-[36px] flex-1 resize-none bg-transparent py-2 text-[14px] leading-6 text-[#18312f] outline-none placeholder:text-[#a8b8b4] disabled:opacity-60"
            />

            <button
              type="button"
              onClick={() => send(draft)}
              disabled={busy || !draft.trim()}
              className="mb-0.5 h-8 rounded-lg bg-[#e7a14d] px-3.5 text-[13px] font-semibold text-[#18312f] transition hover:bg-[#dda044] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Send
            </button>
          </div>

          <p className="mt-2.5 text-[11px] leading-4 text-[#a8b8b4]">
            Spreadsheets and bank CSVs. Nothing is added to your records until you accept it.
          </p>
        </div>
      </div>

      {dragging && (
        <div className="pointer-events-none absolute inset-3 z-30 grid place-items-center rounded-2xl border-2 border-dashed border-[#00947a] bg-[#f5f2e8]/85 backdrop-blur-sm">
          <p className="text-[14px] font-medium text-[#0f5f50]">Drop the statement anywhere here</p>
        </div>
      )}
    </div>
  );
}

function ClipIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M10.8 4.2 5.6 9.4a1.7 1.7 0 0 0 2.4 2.4l5.2-5.2a3.1 3.1 0 0 0-4.4-4.4L3.6 7.4a4.5 4.5 0 0 0 6.4 6.4l4.4-4.4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
