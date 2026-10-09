'use client';

import { Lightbulb, Mic, Paperclip, Plus, SendHorizontal, Sparkles, Square, Telescope } from 'lucide-react';
import { useEffect, useRef } from 'react';

import FileChips from '@/components/chat/FileChips';
import type { Attachment } from '@/lib/useUploads';

/**
 * The composer, pinned to the bottom of the chat pane.
 *
 * The textarea grows with what is typed and then stops, because a question about a
 * portfolio can run to three lines and a fixed single-line input hides the start of
 * it. The height is reset before it is measured — without that, `scrollHeight` only
 * ever reports the tallest the box has been, so it grows and never shrinks.
 *
 * Enter sends and Shift+Enter breaks the line, which is the convention everywhere
 * this kind of box appears.
 *
 * Picking files starts uploading them immediately rather than waiting for Send.
 * Reading a statement takes seconds and so does typing a sentence, and running the
 * two at once is what keeps a reply from being held behind a parser. The chips
 * above the box are where that progress is shown.
 *
 * Send is held while any file is still being read. A message that mentions an
 * attachment the backend has not finished with would be answered without it, and
 * "one moment" is a better answer than a confident one about nothing.
 *
 * While a reply is being written the send button becomes a stop button, so the person can cut a
 * long answer short and keep what was already written.
 *
 * The picker's value is cleared after every pick, so choosing the same file twice
 * in a row still fires a change event.
 *
 * Two layouts, as in the reference. `hero` is the large box in the middle of an empty
 * chat, with the Reasoning and Deep Research pills. `dock` is the box pinned to the
 * bottom once the conversation starts. Both put the text on top and the buttons below.
 *
 * Plus, Mic, Reasoning and Deep Research are drawn but do nothing yet. The backend
 * has no speech-to-text and the agent has no mode switch for them to turn on.
 */

/** What the pipeline can actually read: the deterministic formats first, then the ones a model reads. */
const ACCEPTED =
  '.csv,.xlsx,.xls,.pdf,.png,.jpg,.jpeg,.webp,text/csv,application/pdf,image/png,image/jpeg,image/webp';

export default function ChatComposer({
  value,
  onChange,
  onSend,
  onStop,
  busy,
  inputRef,
  attachments,
  onAttach,
  onRemoveAttachment,
  onUnlockAttachment,
  variant = 'dock',
}: {
  value: string;
  onChange: (next: string) => void;
  onSend: () => void;
  onStop: () => void;
  busy: boolean;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  attachments: Attachment[];
  onAttach: (files: File[]) => void;
  onRemoveAttachment: (key: string) => void;
  onUnlockAttachment: (key: string, password: string) => void;
  variant?: 'hero' | 'dock';
}) {
  const shell = useRef<HTMLDivElement>(null);
  const picker = useRef<HTMLInputElement>(null);

  // Re-measure on every change, resetting first so the box can shrink again.
  useEffect(() => {
    const field = inputRef.current;
    if (!field) return;

    field.style.height = 'auto';
    field.style.height = `${Math.min(field.scrollHeight, 132)}px`;
  }, [value, inputRef]);

  const reading = attachments.some(
    (item) =>
      item.status === 'uploading' || item.status === 'uploaded' || item.status === 'extracting',
  );

  const hero = variant === 'hero';

  return (
    <div className={hero ? 'w-full' : 'px-3 pt-2 pb-3 sm:px-4'}>
      <FileChips
        attachments={attachments}
        onRemove={onRemoveAttachment}
        onUnlock={onUnlockAttachment}
      />

      <div
        ref={shell}
        className="composer-shell rounded-[22px] border border-[var(--pane-border)] bg-panel-subtle/80 px-3 pt-3 pb-2.5 transition"
      >
        <input
          ref={picker}
          type="file"
          multiple
          accept={ACCEPTED}
          className="hidden"
          onChange={(event) => {
            const picked = Array.from(event.target.files ?? []);

            event.target.value = '';

            if (picked.length > 0) onAttach(picked);
          }}
        />

        <div className="flex items-start gap-2 px-1">
          {hero && (
            <Sparkles size={15} className="mt-[9px] flex-none text-secondary" aria-hidden="true" />
          )}

          <label className="sr-only" htmlFor="composer">
            Ask about your money
          </label>

          <textarea
            id="composer"
            ref={inputRef}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                onSend();
              }
            }}
            rows={hero ? 3 : 1}
            placeholder={
              busy
                ? 'One moment…'
                : hero
                  ? 'Start your request, and let Mosaic handle everything.'
                  : 'Ask a question or make a request…'
            }
            className={`max-h-[132px] flex-1 resize-none bg-transparent py-1.5 text-[13.5px] leading-[1.5] text-primary outline-none placeholder:text-muted ${
              hero ? 'min-h-[76px]' : 'min-h-[36px]'
            }`}
          />
        </div>

        <div className="mt-2 flex items-center gap-1.5">
          {!hero && (
            <button type="button" aria-label="More actions" title="More actions" className="icon-pill h-9 w-9">
              <Plus size={16} aria-hidden="true" />
            </button>
          )}

          <button
            type="button"
            onClick={() => picker.current?.click()}
            aria-label="Attach a statement"
            title="Attach a bank or holdings statement"
            className="icon-pill h-9 w-9"
          >
            <Paperclip size={15} aria-hidden="true" />
          </button>

          {hero && (
            <>
              <ModePill icon={<Lightbulb size={14} aria-hidden="true" />}>Reasoning</ModePill>
              <ModePill icon={<Telescope size={14} aria-hidden="true" />}>Deep Research</ModePill>
            </>
          )}

          <div className="ml-auto flex items-center gap-1.5">
            <button type="button" aria-label="Speak your request" title="Speak your request" className="icon-pill h-9 w-9">
              <Mic size={15} aria-hidden="true" />
            </button>

            {busy ? (
              <button
                type="button"
                onClick={onStop}
                aria-label="Stop response"
                title="Stop response"
                className="send-gradient grid h-10 w-10 place-items-center rounded-full transition"
              >
                <Square size={13} fill="currentColor" aria-hidden="true" />
              </button>
            ) : (
              <button
                type="button"
                onClick={onSend}
                disabled={reading || !value.trim()}
                aria-label="Send message"
                className="send-gradient grid h-10 w-10 place-items-center rounded-full transition disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none"
              >
                <SendHorizontal size={16} strokeWidth={2.4} aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      </div>

      {reading && <p className="mt-2 text-center text-[11px] text-muted">Reading your files…</p>}
    </div>
  );
}

/** A labelled pill in the hero composer's toolbar. Drawn only, for now. */
function ModePill({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      type="button"
      className="inline-flex h-9 items-center gap-1.5 rounded-full border border-[var(--pane-border)] bg-panel-subtle px-3 text-[12px] text-secondary transition hover:border-line-strong hover:text-primary max-sm:hidden"
    >
      {icon}
      {children}
    </button>
  );
}
