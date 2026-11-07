'use client';

import { ChartNoAxesCombined, ChevronRight, PieChart, ShieldCheck, Sparkles, Target } from 'lucide-react';

import { Badge, type Icon } from '@/components/blocks/Tile';

/**
 * Openings, for a blank conversation that would otherwise ask for a cold start.
 *
 * Glass tiles under the hero composer: one column on a phone, two once there is room.
 * The questions are sentences, so each tile wraps rather than truncating.
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

/** One small icon per opener, in the same order. */
const ICONS: Icon[] = [Target, ChartNoAxesCombined, PieChart, ShieldCheck];

export default function SuggestedPrompts({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <section aria-label="Suggested questions">
      <p className="mb-2.5 flex items-center gap-1.5 text-[13.5px] font-medium text-secondary">
        <Sparkles size={13} style={{ color: 'var(--accent)' }} aria-hidden="true" />
        Suggested for you
      </p>

      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {OPENERS.map((prompt, index) => (
          <li key={prompt}>
            <button
              type="button"
              onClick={() => onPick(prompt)}
              className="tone-accent flex h-full w-full items-center gap-2.5 rounded-2xl border border-[var(--pane-border)] bg-panel-subtle/70 px-3 py-2.5 text-left text-[14px] leading-[1.4] text-secondary transition hover:border-line-strong hover:text-primary"
            >
              <Badge icon={ICONS[index % ICONS.length]} small />
              <span className="min-w-0 flex-1">{prompt}</span>
              <ChevronRight size={14} className="flex-none text-muted" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
