'use client';

import { ChevronRight, Sparkles } from 'lucide-react';

/**
 * Openings, for a blank conversation that would otherwise ask for a cold start.
 *
 * Full-width rows rather than wrapped pills. The questions are sentences and the
 * chat pane is narrow; pills would break them across two lines each and the block
 * would read as a paragraph cut into pieces.
 *
 * They disappear once the conversation begins. A suggestion is scaffolding for an
 * empty screen, and leaving it under a real exchange competes with the answer.
 */

export const OPENERS = [
  'How can I reach my home buying goal faster?',
  'Am I on track for retirement?',
  'Review my portfolio risk',
  'Show me tax saving opportunities for this year.',
];

export default function SuggestedPrompts({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <section aria-label="Suggested questions" className="px-4 sm:px-5">
      <p className="mb-2.5 flex items-center gap-1.5 text-[12px] font-medium text-secondary">
        <Sparkles size={13} style={{ color: 'var(--accent)' }} aria-hidden="true" />
        Suggested for you
      </p>

      <ul className="space-y-2">
        {OPENERS.map((prompt) => (
          <li key={prompt}>
            <button
              type="button"
              onClick={() => onPick(prompt)}
              className="flex w-full items-center gap-2 rounded-xl border border-line bg-panel px-3.5 py-2.5 text-left text-[12.5px] leading-[1.4] text-primary transition hover:border-line-strong hover:bg-panel-subtle"
            >
              <span className="min-w-0 flex-1">{prompt}</span>
              <ChevronRight size={14} className="flex-none text-muted" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
