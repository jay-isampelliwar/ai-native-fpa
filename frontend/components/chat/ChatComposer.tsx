'use client';

import { Paperclip, SendHorizontal } from 'lucide-react';
import { useEffect, useRef } from 'react';

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
 * The attach control is present and does nothing yet. The backend has no document
 * endpoints, so there is nothing for a chosen file to be sent to — it is drawn
 * because the reference shows it and because the composer's proportions depend on
 * it, and it says so rather than opening a picker that leads nowhere.
 */
export default function ChatComposer({
  value,
  onChange,
  onSend,
  busy,
  inputRef,
}: {
  value: string;
  onChange: (next: string) => void;
  onSend: () => void;
  busy: boolean;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
}) {
  const shell = useRef<HTMLDivElement>(null);

  // Re-measure on every change, resetting first so the box can shrink again.
  useEffect(() => {
    const field = inputRef.current;
    if (!field) return;

    field.style.height = 'auto';
    field.style.height = `${Math.min(field.scrollHeight, 132)}px`;
  }, [value, inputRef]);

  return (
    <div className="border-t border-line bg-background/85 px-4 py-3.5 backdrop-blur-xl sm:px-5">
      <div
        ref={shell}
        className="composer-shell flex items-end gap-1.5 rounded-2xl border border-line bg-panel px-2 py-1.5 transition"
      >
        <button
          type="button"
          disabled
          aria-label="Attach a file — not available yet"
          title="File uploads are not available yet"
          className="grid h-9 w-9 flex-none cursor-not-allowed place-items-center rounded-xl text-muted opacity-60"
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
          disabled={busy || !value.trim()}
          aria-label="Send message"
          className="mb-0.5 grid h-9 w-9 flex-none place-items-center rounded-xl transition disabled:cursor-not-allowed disabled:opacity-40"
          style={{ background: 'var(--accent)', color: 'var(--on-accent)' }}
        >
          <SendHorizontal size={16} strokeWidth={2.4} aria-hidden="true" />
        </button>
      </div>

      <p className="mt-2 text-center text-[11px] text-muted">
        Enter to send · Shift + Enter for a new line
      </p>
    </div>
  );
}
