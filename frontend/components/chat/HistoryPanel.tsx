'use client';

import { MessageCircle, Plus, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { conversations } from '@/lib/api';
import type { ConversationSummary } from '@/lib/types';

/**
 * The list of past chats, with New Chat at the top, as in the reference.
 *
 * Chats are grouped by how long ago they were last active: Today, Yesterday, then
 * "N Days Ago" for the last month, then the month itself. The order inside a group
 * is the backend's, newest activity first.
 *
 * The list is fetched again whenever `version` changes. The shell bumps it when a
 * message starts a new chat and when a reply finishes, so a new chat appears at once
 * and a chat that just got a reply moves to the top.
 *
 * A failed fetch keeps whatever list was already showing and says so underneath,
 * rather than blanking the panel.
 */
export default function HistoryPanel({
  activeId,
  version,
  onSelect,
  onNewChat,
  onClose,
}: {
  activeId: number | null;
  version: number;
  onSelect: (conversationId: number) => void;
  onNewChat: () => void;
  /** Set on small screens, where the panel is a drawer that needs a close button. */
  onClose?: () => void;
}) {
  const [items, setItems] = useState<ConversationSummary[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;

    conversations
      .list()
      .then((result) => {
        if (!live) return;

        setItems(result.conversations);
        setFailed(false);
      })
      .catch(() => {
        if (live) setFailed(true);
      });

    return () => {
      live = false;
    };
  }, [version]);

  const groups = groupByDay(items ?? [], new Date());

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 px-4 pt-4 pb-3">
        <h2 className="text-[17px] font-semibold tracking-[-0.01em] text-primary">History Chat</h2>

        <button
          type="button"
          onClick={onNewChat}
          className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-full border border-[var(--pane-border)] bg-background px-3.5 text-[12.5px] font-medium text-primary transition hover:border-line-strong"
        >
          <Plus size={14} aria-hidden="true" />
          New Chat
        </button>

        {onClose && (
          <button type="button" onClick={onClose} aria-label="Close history" className="icon-pill h-9 w-9">
            <X size={15} aria-hidden="true" />
          </button>
        )}
      </header>

      <nav aria-label="Past conversations" className="quiet-scroll min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        {items === null && !failed && <p className="px-1 pt-2 text-[12px] text-muted">Loading chats…</p>}

        {items?.length === 0 && (
          <p className="px-1 pt-2 text-[12px] leading-[1.5] text-muted">
            No chats yet. Your conversations will appear here.
          </p>
        )}

        {groups.map((group) => (
          <section key={group.label} className="mt-2 first:mt-0">
            <h3 className="px-1 pt-2 pb-2 text-[12px] font-medium text-secondary">{group.label}</h3>

            <ul className="space-y-2">
              {group.items.map((item) => {
                const active = item.id === activeId;

                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(item.id)}
                      aria-current={active ? 'true' : undefined}
                      title={item.title}
                      className="flex w-full items-center gap-2.5 rounded-2xl border px-2 py-2 text-left transition hover:border-line-strong"
                      style={
                        active
                          ? { borderColor: 'var(--accent-soft)', background: 'var(--panel-elevated)' }
                          : { borderColor: 'var(--pane-border)', background: 'var(--panel-subtle)' }
                      }
                    >
                      <span
                        aria-hidden="true"
                        className="grid h-8 w-8 flex-none place-items-center rounded-full border border-[var(--pane-border)] bg-background"
                        style={{ color: active ? 'var(--accent)' : 'var(--text-secondary)' }}
                      >
                        <MessageCircle size={14} />
                      </span>

                      <span
                        className={`min-w-0 flex-1 truncate text-[12.5px] ${
                          active ? 'text-primary' : 'text-secondary'
                        }`}
                      >
                        {item.title}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}

        {failed && (
          <p className="px-1 pt-3 text-[12px] text-negative">Could not load your chats. Is the backend running?</p>
        )}
      </nav>
    </div>
  );
}

interface DayGroup {
  label: string;
  items: ConversationSummary[];
}

/** Whole calendar days between two moments, in the reader's own time zone. */
function daysBetween(earlier: Date, later: Date): number {
  const start = new Date(earlier.getFullYear(), earlier.getMonth(), earlier.getDate());
  const end = new Date(later.getFullYear(), later.getMonth(), later.getDate());

  return Math.round((end.getTime() - start.getTime()) / 86_400_000);
}

function dayLabel(updatedAt: Date, now: Date): string {
  const days = daysBetween(updatedAt, now);

  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 30) return `${days} Days Ago`;

  return updatedAt.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
}

/** Keep the backend's order and start a new group each time the label changes. */
function groupByDay(items: ConversationSummary[], now: Date): DayGroup[] {
  const groups: DayGroup[] = [];

  for (const item of items) {
    const label = dayLabel(new Date(item.updated_at), now);
    const last = groups.at(-1);

    if (last?.label === label) last.items.push(item);
    else groups.push({ label, items: [item] });
  }

  return groups;
}
