'use client';

import { Moon, PanelLeftClose, Sun } from 'lucide-react';

import { useTheme } from '@/lib/theme';

/**
 * The chat pane's header: the mark, the product, and the theme control.
 *
 * No navigation. The doc is explicit that this application has two regions and no
 * third rail, so the only control here is the one that belongs to the frame rather
 * than to the conversation.
 *
 * The toggle says what it will do, not what is currently true. A button labelled
 * "Dark" in dark mode reads as a statement; labelled "Switch to light theme" it
 * reads as an action, which is what a button is.
 */
export default function ChatHeader({ onCollapse }: { onCollapse?: () => void }) {
  const { theme, toggle } = useTheme();

  const next = theme === 'dark' ? 'light' : 'dark';
  const Icon = theme === 'dark' ? Sun : Moon;

  return (
    <header className="flex items-center gap-3 px-4 pt-5 pb-4 sm:px-5">
      <Logo />

      <div className="min-w-0">
        <p className="truncate text-[17px] leading-none font-bold tracking-[-0.01em] text-primary">
          Mosaic
        </p>
        <p className="mt-1 truncate text-[11.5px] text-secondary">Your AI financial planner</p>
      </div>

      <div className="ml-auto flex flex-none items-center gap-1.5">
        <button
          type="button"
          onClick={toggle}
          aria-label={`Switch to ${next} theme`}
          title={`Switch to ${next} theme`}
          className="grid h-8 w-8 place-items-center rounded-full border border-line bg-panel-subtle text-secondary transition hover:border-line-strong hover:text-primary"
        >
          <Icon size={15} aria-hidden="true" />
        </button>

        {onCollapse && (
          <button
            type="button"
            onClick={onCollapse}
            aria-label="Reset panel width"
            title="Reset panel width"
            className="hidden h-8 w-8 place-items-center rounded-full border border-line bg-panel-subtle text-secondary transition hover:border-line-strong hover:text-primary lg:grid"
          >
            <PanelLeftClose size={15} aria-hidden="true" />
          </button>
        )}
      </div>
    </header>
  );
}

/** The mark: four tiles, one lit — a mosaic, and the shape of a rising bar chart. */
function Logo() {
  return (
    <span
      aria-hidden="true"
      className="grid h-9 w-9 flex-none place-items-center rounded-xl"
      style={{ background: 'var(--accent-soft)' }}
    >
      <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none">
        <rect x="2" y="11" width="6" height="7" rx="2" fill="var(--accent)" opacity="0.55" />
        <rect x="2" y="2" width="6" height="7" rx="2" fill="var(--accent)" opacity="0.3" />
        <rect x="12" y="11" width="6" height="7" rx="2" fill="var(--accent)" opacity="0.3" />
        <rect x="12" y="2" width="6" height="7" rx="2" fill="var(--accent)" />
      </svg>
    </span>
  );
}
