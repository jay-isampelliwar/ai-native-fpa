'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, conversations, runs } from '@/lib/api';
import { firstNameOf } from '@/lib/format';
import { useSession } from '@/lib/session';
import { cancelRun, followRun, streamMessage, type Outgoing, type StreamHandlers } from '@/lib/stream';
import type {
  ApprovalDecision,
  ApprovalEdits,
  ApprovalState,
  ConversationDetail,
  FormBlock,
  FormSubmission,
  FormValue,
  ToolStep,
  UiBlockEntry,
} from '@/lib/types';
import { useUploads } from '@/lib/useUploads';
import ChatComposer from '@/components/chat/ChatComposer';
import ChatHeader from '@/components/chat/ChatHeader';
import FormPanel from '@/components/forms/FormPanel';
import MessageTimeline, { type Turn } from '@/components/chat/MessageTimeline';
import SuggestedPrompts from '@/components/chat/SuggestedPrompts';
import Orb from '@/components/ui/Orb';
import ThinkingOrb from '@/components/ui/ThinkingOrb';
import { orbStateForTool } from '@/lib/orb/tools';

const newId = () => Math.random().toString(36).slice(2, 10);

/** "Good morning" before noon, "Good afternoon" until five, "Good evening" after. */
function greeting(now: Date): string {
  const hour = now.getHours();

  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';

  return 'Good evening';
}

/** Replace the step with the same id, or add it at the end if it is new. */
function upsertStep(steps: ToolStep[], step: ToolStep): ToolStep[] {
  return steps.some((item) => item.id === step.id)
    ? steps.map((item) => (item.id === step.id ? step : item))
    : [...steps, step];
}

/** Replace the block with the same id, or add it at the end if it is new. */
function upsertBlock(blocks: UiBlockEntry[], entry: UiBlockEntry): UiBlockEntry[] {
  return blocks.some((item) => item.id === entry.id)
    ? blocks.map((item) => (item.id === entry.id ? entry : item))
    : [...blocks, entry];
}

/** The form open beside the chat: which reply and block opened it, and what it starts with. */
interface OpenForm {
  answerId: string;
  blockId: string;
  block: FormBlock;
}

/** Mark every step still running as ended, for a reply that was stopped or failed. */
function closeSteps(steps: ToolStep[] | undefined, status: 'stopped' | 'error'): ToolStep[] | undefined {
  return steps?.map((step) => (step.status === 'running' ? { ...step, status } : step));
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
    tools: message.tools,
    blocks: message.blocks ?? [],
    form: message.form ?? null,
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
 *
 * A reply can pause on an approval card, such as before a delete. The stream ends there and the
 * composer frees up. Pressing Remove or Keep it tells the backend and listens to the same run again.
 * Sending a new message instead counts as a reject on the backend, so the card shows as skipped.
 *
 * A tool can open a form. It opens on the right half of the screen with the chat on the left, and
 * `onFormChange` tells the shell to hide the history list so each side gets half. On a phone the form
 * covers the screen. Sending it starts a turn like a typed message, with the form instead of text.
 * Closing it tells no one; the reply that opened it keeps a button to open it again.
 */
export default function ChatWorkspace({
  userId,
  openConversationId = null,
  onActivity,
  onShowHistory,
  onFormChange,
}: {
  userId: number | null;
  openConversationId?: number | null;
  onActivity?: (conversationId: number) => void;
  onShowHistory?: () => void;
  onFormChange?: (open: boolean) => void;
}) {
  const [form, setForm] = useState<OpenForm | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  // Where the reply is: waiting for the run to start, or the planner at work. Null when idle.
  const [step, setStep] = useState<'connecting' | 'thinking' | null>(null);
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
    onFormChange?.(form !== null);
  }, [form, onFormChange]);

  // The shell shows the history list again when this pane goes away with a form still open.
  useEffect(() => () => onFormChange?.(false), [onFormChange]);

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
        setStep('thinking');
        setConversationId(run.conversation_id);
        onActivity?.(run.conversation_id);
        runId.current = run.run_id;
        if (stopWanted.current) void cancelRun(run.run_id);
      },
      onSnapshot: (text) => {
        setStep('thinking');
        amend((turn) => ({ ...turn, text }));
      },
      onToken: (piece) => {
        setStep('thinking');
        amend((turn) => ({ ...turn, text: turn.text + piece }));
      },
      onTool: (tool) => {
        setStep('thinking');
        amend((turn) => ({ ...turn, tools: upsertStep(turn.tools ?? [], tool) }));
      },
      onBlock: (entry) => {
        amend((turn) => ({ ...turn, blocks: upsertBlock(turn.blocks ?? [], entry) }));
        if (entry.block.type === 'form') setForm({ answerId, blockId: entry.id, block: entry.block });
      },
      onApproval: (request) =>
        amend((turn) => ({ ...turn, approval: { request, state: 'pending', at: turn.text.length } })),
      onDone: (text) => amend((turn) => ({ ...turn, text })),
      onCancelled: (text) =>
        amend((turn) => ({ ...turn, text: text || turn.text, stopped: true, tools: closeSteps(turn.tools, 'stopped') })),
      onError: (message) =>
        amend((turn) => ({ ...turn, text: turn.text || message, failed: true, tools: closeSteps(turn.tools, 'error') })),
    };
  }

  /** Run one stream to its end, then reset the working state. A pane that was left says nothing. */
  async function listen(answerId: string, start: (handlers: StreamHandlers, signal?: AbortSignal) => Promise<void>) {
    const signal = listening.current?.signal;
    const handlers = handlersFor(answerId);

    setBusy(true);
    setStep('connecting');

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

  /** Set where one turn's approval card is, and its error line, if any. */
  function setApproval(answerId: string, state: ApprovalState, failure?: string) {
    setTurns((current) =>
      current.map((turn) =>
        turn.id === answerId && turn.approval ? { ...turn, approval: { ...turn.approval, state, failure } } : turn,
      ),
    );
  }

  /** Answer an approval card, with any values fixed on a confirm card, then follow the run again as it carries on. */
  async function decide(answerId: string, decision: ApprovalDecision, edits?: ApprovalEdits) {
    const request = turns.find((turn) => turn.id === answerId)?.approval?.request;
    if (!request || busy) return;

    setApproval(answerId, 'sending');

    try {
      await runs.decide(request.run_id, request.approval_id, decision, edits);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setApproval(answerId, error.message.includes('expired') ? 'expired' : 'closed', error.message);
      } else {
        setApproval(answerId, 'pending', 'That did not go through. Please try again.');
      }
      return;
    }

    setApproval(answerId, decision === 'approve' ? 'approved' : 'rejected');

    runId.current = request.run_id;
    await listen(answerId, (handlers, signal) => followRun(request.run_id, handlers, signal));
  }

  /** Start one turn from typed words or a filled form, with the user turn drawn first. */
  async function start(outgoing: Outgoing, shown: { text: string; form?: FormSubmission }) {
    if (busy || loading || uploads.reading || typeof userId !== 'number') return;

    const answerId = newId();

    // Read before clearing: the chips are emptied as the message is sent, and these ids are what
    // ties the reply to the files it is about.
    const importIds = uploads.importIds;
    const attached = uploads.attachments.map((item) => item.name);

    if (!shown.form) setDraft('');
    uploads.clear();
    setTurns((current) => [
      ...current.map((turn) =>
        turn.approval?.state === 'pending' ? { ...turn, approval: { ...turn.approval, state: 'skipped' as const } } : turn,
      ),
      { id: newId(), role: 'user', text: shown.text, at: new Date(), attached, form: shown.form ?? null },
      { id: answerId, role: 'planner', text: '', at: new Date(), importIds },
    ]);

    await listen(answerId, (handlers, signal) => streamMessage(conversationId, outgoing, handlers, signal));
  }

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed) return;

    await start({ message: trimmed }, { text: trimmed });
  }

  /** Send the open form's values as the next turn and close the form. */
  async function sendForm(values: Record<string, FormValue>) {
    if (!form || busy) return;

    const submission: FormSubmission = {
      kind: form.block.form,
      values,
      record_id: form.block.record_id,
      block_id: form.blockId,
    };

    setForm(null);
    await start({ form: submission }, { text: '', form: submission });
  }

  /** Open again the form a reply gave, from its button. */
  function openForm(answerId: string, blockId: string) {
    const entry = turns.find((turn) => turn.id === answerId)?.blocks?.find((item) => item.id === blockId);

    if (entry?.block.type === 'form') setForm({ answerId, blockId, block: entry.block });
  }

  const closeForm = useCallback(() => setForm(null), []);

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

    if (question?.form) void start({ form: question.form }, { text: '', form: question.form });
    else if (question) void send(question.text);
  }

  const streamingId = busy ? turns.at(-1)?.id : undefined;

  // The pill follows the newest tool still running; between tools it says the planner is thinking.
  const runningTool = turns.at(-1)?.tools?.findLast((tool) => tool.status === 'running');
  const pill = runningTool
    ? { state: orbStateForTool(runningTool.name), label: `${runningTool.label}…` }
    : step === 'connecting'
      ? { state: 'connecting' as const, label: 'Connecting…' }
      : { state: 'breathing' as const, label: 'Thinking…' };
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
    <div className="flex h-full min-h-0">
      <main aria-label="Conversation" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <ChatHeader started={!empty} onShowHistory={onShowHistory} />

        {/* min-h-0 is load-bearing: without it this flex child will not shrink below
            its content, so it never scrolls and the column grows past the viewport. */}
        <div ref={scroller} className="quiet-scroll min-h-0 flex-1 overflow-y-auto pb-4">
          {empty ? (
            <div className="flex min-h-full flex-col items-center justify-center px-4 py-8 sm:px-8">
              <Orb size={76} />

              <h2 className="mt-6 max-w-[22ch] text-center text-[28px] leading-[1.3] font-semibold tracking-[-0.015em] text-primary">
                {greeting(new Date())}{firstName ? `, ${firstName}` : ''}! How can I assist you?
              </h2>

              <div className="mt-8 w-full max-w-[768px]">
                <ChatComposer {...composerProps} variant="hero" />
              </div>

              <div className="mt-6 w-full max-w-[768px]">
                <SuggestedPrompts onPick={send} />
              </div>
            </div>
          ) : loading ? (
            <p className="mx-auto max-w-[816px] px-6 pt-4 text-[14px] text-muted">Loading conversation…</p>
          ) : loadFailed ? (
            <p className="mx-auto max-w-[816px] px-6 pt-4 text-[14px] text-negative">
              This conversation could not be opened. Start a new chat or try again.
            </p>
          ) : (
            <MessageTimeline
              turns={turns}
              streamingId={streamingId}
              userId={userId}
              busy={busy}
              openFormId={form?.blockId ?? null}
              onRegenerate={regenerate}
              onDecide={(answerId, decision, edits) => void decide(answerId, decision, edits)}
              onOpenForm={openForm}
            />
          )}

          {step && (
            <div className="mx-auto mt-3 w-full max-w-[816px] px-4 sm:px-6">
              <p
                aria-live="polite"
                className="inline-flex items-center gap-2.5 rounded-full border border-[var(--pane-border)] bg-panel-subtle py-1.5 pr-4 pl-2"
              >
                <ThinkingOrb state={pill.state} size={22} label="" />
                <span className="thinking-shimmer text-[14px] font-medium">{pill.label}</span>
              </p>
            </div>
          )}
        </div>

        {!empty && (
          <div className="mx-auto w-full max-w-[816px] px-1 sm:px-2">
            <ChatComposer {...composerProps} />
          </div>
        )}
      </main>

      <AnimatePresence>
        {form && (
          <motion.aside
            key={form.blockId}
            aria-label="Form"
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 24 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="fixed inset-0 z-50 min-h-0 overflow-hidden bg-panel-subtle lg:static lg:inset-auto lg:z-auto lg:flex-1 lg:border-l lg:border-[var(--pane-border)]"
          >
            <FormPanel
              kind={form.block.form}
              initial={form.block.values}
              editing={form.block.record_id !== null}
              busy={busy}
              onSend={(values) => void sendForm(values)}
              onClose={closeForm}
            />
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
}
