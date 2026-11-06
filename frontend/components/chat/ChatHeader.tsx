'use client';

import { EllipsisVertical, History, Moon, Sun } from 'lucide-react';

import { useTheme } from '@/lib/theme';
import Orb from '@/components/ui/Orb';
import UserMenu from '@/components/ui/UserMenu';

/**
 * The chat pane's header: the assistant badge, the theme switch, and two menus.
 *
 * Before the first message the header shows only the badge, as the reference does.
 * Once a conversation starts it reads "AI Chat", so the pane says what it holds.
 *
 * The theme switch is a two-sided pill, sun and moon, with the current side lit.
 * Each side is a button that names the theme it turns on.
 *
 * History opens the chat list as a drawer on small screens. On wide screens the list
 * is always beside the chat, so the button is hidden there. The more menu is drawn
 * but does nothing yet. The avatar at the end opens the account menu with sign out.
 */
export default function ChatHeader({
  started,
  onShowHistory,
}: {
  started: boolean;
  onShowHistory?: () => void;
}) {
  const { theme, toggle } = useTheme();

  return (
    <header className="flex items-center gap-3 px-4 pt-4 pb-3 sm:px-5">
      {started ? (
        <h1 className="text-[18px] font-semibold tracking-[-0.01em] text-primary">AI Chat</h1>
      ) : (
        <span className="inline-flex items-center gap-2 rounded-full border border-[var(--pane-border)] bg-panel-subtle py-1 pr-3.5 pl-1">
          <Orb size={26} />
          <span className="text-[14px] font-medium text-primary">Mosaic AI</span>
        </span>
      )}

      <div className="ml-auto flex flex-none items-center gap-1.5">
        <div className="flex items-center gap-0.5 rounded-full border border-[var(--pane-border)] bg-panel-subtle p-0.5">
          <ThemeSide active={theme === 'light'} label="Switch to light theme" onPick={toggle}>
            <Sun size={14} aria-hidden="true" />
          </ThemeSide>
          <ThemeSide active={theme === 'dark'} label="Switch to dark theme" onPick={toggle}>
            <Moon size={14} aria-hidden="true" />
          </ThemeSide>
        </div>

        <button
          type="button"
          onClick={onShowHistory}
          aria-label="Chat history"
          title="Chat history"
          className="icon-pill h-8 w-8 lg:hidden"
        >
          <History size={15} aria-hidden="true" />
        </button>

        <button type="button" aria-label="More options" title="More options" className="icon-pill h-8 w-8">
          <EllipsisVertical size={15} aria-hidden="true" />
        </button>

        <UserMenu />
      </div>
    </header>
  );
}

/** One side of the theme pill. Pressing the side that is already lit does nothing. */
function ThemeSide({
  active,
  label,
  onPick,
  children,
}: {
  active: boolean;
  label: string;
  onPick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      title={label}
      onClick={active ? undefined : onPick}
      className="grid h-7 w-7 place-items-center rounded-full transition"
      style={
        active
          ? { background: 'var(--panel-elevated)', color: 'var(--accent)', boxShadow: '0 0 0 1px var(--accent-soft)' }
          : { color: 'var(--text-muted)' }
      }
    >
      {children}
    </button>
  );
}
