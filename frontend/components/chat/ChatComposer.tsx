'use client';

import { Paperclip, SendHorizontal } from 'lucide-react';
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
 * The picker's value is cleared after every pick, so choosing the same file twice
 * in a row still fires a change event.
 */

/** What the pipeline can actually read: the deterministic formats first, then the ones a model reads. */
const ACCEPTED =
  '.csv,.xlsx,.xls,.pdf,.png,.jpg,.jpeg,.webp,text/csv,application/pdf,image/png,image/jpeg,image/webp';

export default function ChatComposer({
  value,
  onChange,
  onSend,
  busy,
  inputRef,
  attachments,
  onAttach,
  onRemoveAttachment,
  onUnlockAttachment,
}: {
  value: string;
  onChange: (next: string) => void;
  onSend: () => void;
  busy: boolean;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  attachments: Attachment[];
  onAttach: (files: File[]) => void;
  onRemoveAttachment: (key: string) => void;
  onUnlockAttachment: (key: string, password: string) => void;
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

  return (
    <div className="border-t border-line bg-background/85 px-4 py-3.5 backdrop-blur-xl sm:px-5">
      <FileChips
        attachments={attachments}
        onRemove={onRemoveAttachment}
        onUnlock={onUnlockAttachment}
      />

      <div
        ref={shell}
        className="composer-shell flex items-end gap-1.5 rounded-2xl border border-line bg-panel px-2 py-1.5 transition"
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

        <button
          type="button"
          onClick={() => picker.current?.click()}
          aria-label="Attach a statement"
          title="Attach a bank or holdings statement"
          className="grid h-9 w-9 flex-none place-items-center rounded-xl text-muted transition hover:bg-panel-subtle hover:text-primary"
        >
          <Paperclip size={16} aria-hidden="true" />
        </button>

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
          rows={1}
          placeholder={busy ? 'One moment…' : 'Ask about your money…'}
          className="max-h-[132px] min-h-[36px] flex-1 resize-none bg-transparent py-2 text-[13.5px] leading-[1.5] text-primary outline-none placeholder:text-muted"
        />

        <button
          type="button"
          onClick={onSend}
          disabled={busy || reading || !value.trim()}
          aria-label="Send message"
          className="mb-0.5 grid h-9 w-9 flex-none place-items-center rounded-xl transition disabled:cursor-not-allowed disabled:opacity-40"
          style={{ background: 'var(--accent)', color: 'var(--on-accent)' }}
        >
          <SendHorizontal size={16} strokeWidth={2.4} aria-hidden="true" />
        </button>
      </div>

      <p className="mt-2 text-center text-[11px] text-muted">
        {reading ? 'Reading your files…' : 'Enter to send · Shift + Enter for a new line'}
      </p>
    </div>
  );
}
