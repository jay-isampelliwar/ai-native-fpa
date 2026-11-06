'use client';

import { MessageCircle, Pencil, Plus, Trash2, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { ApiError, conversations } from '@/lib/api';
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
 *
 * Each row has a pencil and a trash button. The pencil turns the row into a title
 * input; Enter saves and Escape cancels. The trash asks to confirm inside the row,
 * then soft deletes the chat on the backend and drops it from the list.
 */
export default function HistoryPanel({
  activeId,
  version,
  onSelect,
  onNewChat,
  onDeleted,
  onClose,
}: {
  activeId: number | null;
  version: number;
  onSelect: (conversationId: number) => void;
  onNewChat: () => void;
  /** Called after a chat is deleted, so the shell can leave it if it was open. */
  onDeleted: (conversationId: number) => void;
  /** Set on small screens, where the panel is a drawer that needs a close button. */
  onClose?: () => void;
}) {
  const [items, setItems] = useState<ConversationSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [editing, setEditing] = useState<{ id: number; draft: string } | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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

  async function remove(conversationId: number) {
    setDeletingId(conversationId);
    setActionError(null);

    try {
      await conversations.remove(conversationId);

      setItems((current) => current?.filter((item) => item.id !== conversationId) ?? null);
      setConfirmingId(null);
      onDeleted(conversationId);
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : 'Could not delete this chat.');
    } finally {
      setDeletingId(null);
    }
  }

  async function rename(conversationId: number, draft: string) {
    const title = draft.trim();
    const current = items?.find((item) => item.id === conversationId);

    if (!title || title === current?.title) {
      setEditing(null);
      return;
    }

    setSavingId(conversationId);
    setActionError(null);

    try {
      const saved = await conversations.rename(conversationId, title);

      setItems((list) => list?.map((item) => (item.id === conversationId ? { ...item, title: saved.title } : item)) ?? null);
      setEditing(null);
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : 'Could not rename this chat.');
    } finally {
      setSavingId(null);
    }
  }

  const groups = groupByDay(items ?? [], new Date());

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 px-4 pt-4 pb-3">
        <h2 className="text-[17px] font-semibold tracking-[-0.01em] text-primary">History Chat</h2>

        <button
          type="button"
          onClick={onNewChat}
          className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-full border border-[var(--pane-border)] bg-background px-3.5 text-[14px] font-medium text-primary transition hover:border-line-strong"
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
        {items === null && !failed && <p className="px-1 pt-2 text-[13.5px] text-muted">Loading chats…</p>}

        {items?.length === 0 && (
          <p className="px-1 pt-2 text-[13.5px] leading-[1.5] text-muted">
            No chats yet. Your conversations will appear here.
          </p>
        )}

        {groups.map((group) => (
          <section key={group.label} className="mt-2 first:mt-0">
            <h3 className="px-1 pt-2 pb-2 text-[13.5px] font-medium text-secondary">{group.label}</h3>

            <ul className="space-y-2">
              {group.items.map((item) => {
                const active = item.id === activeId;

                if (item.id === editing?.id) {
                  const saving = savingId === item.id;

                  return (
                    <li key={item.id}>
                      <form
                        onSubmit={(event) => {
                          event.preventDefault();
                          rename(item.id, editing.draft);
                        }}
                        className="flex w-full items-center gap-2 rounded-2xl border px-2 py-1.5"
                        style={{ borderColor: 'var(--accent-soft)', background: 'var(--panel-elevated)' }}
                      >
                        <input
                          autoFocus
                          value={editing.draft}
                          maxLength={255}
                          disabled={saving}
                          aria-label="Chat title"
                          onChange={(event) => setEditing({ id: item.id, draft: event.target.value })}
                          onKeyDown={(event) => {
                            if (event.key === 'Escape') setEditing(null);
                          }}
                          onFocus={(event) => event.target.select()}
                          className="min-w-0 flex-1 bg-transparent px-1 py-1 text-[14px] text-primary outline-none"
                        />

                        <button
                          type="button"
                          onClick={() => setEditing(null)}
                          disabled={saving}
                          className="rounded-full px-2.5 py-1 text-[13.5px] text-secondary transition hover:text-primary"
                        >
                          Cancel
                        </button>

                        <button
                          type="submit"
                          disabled={saving || !editing.draft.trim()}
                          className="rounded-full border border-[var(--pane-border)] px-2.5 py-1 text-[13.5px] font-medium text-primary transition hover:border-line-strong disabled:opacity-60"
                        >
                          {saving ? 'Saving…' : 'Save'}
                        </button>
                      </form>
                    </li>
                  );
                }

                if (item.id === confirmingId) {
                  const deleting = deletingId === item.id;

                  return (
                    <li key={item.id}>
                      <div
                        className="flex w-full items-center gap-2 rounded-2xl border px-3 py-2"
                        style={{ borderColor: 'var(--pane-border)', background: 'var(--panel-elevated)' }}
                      >
                        <span className="min-w-0 flex-1 truncate text-[14px] text-primary">Delete this chat?</span>

                        <button
                          type="button"
                          onClick={() => setConfirmingId(null)}
                          disabled={deleting}
                          className="rounded-full px-2.5 py-1 text-[13.5px] text-secondary transition hover:text-primary"
                        >
                          Cancel
                        </button>

                        <button
                          type="button"
                          onClick={() => remove(item.id)}
                          disabled={deleting}
                          className="rounded-full border border-[var(--pane-border)] px-2.5 py-1 text-[13.5px] font-medium text-negative transition hover:border-line-strong disabled:opacity-60"
                        >
                          {deleting ? 'Deleting…' : 'Delete'}
                        </button>
                      </div>
                    </li>
                  );
                }

                return (
                  <li key={item.id} className="group relative">
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
                        className={`min-w-0 flex-1 truncate pr-14 text-[14px] ${
                          active ? 'text-primary' : 'text-secondary'
                        }`}
                      >
                        {item.title}
                      </span>
                    </button>

                    <div className="absolute top-1/2 right-2 flex -translate-y-1/2 items-center opacity-0 transition focus-within:opacity-100 group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={() => {
                          setActionError(null);
                          setConfirmingId(null);
                          setEditing({ id: item.id, draft: item.title });
                        }}
                        aria-label={`Rename chat: ${item.title}`}
                        title="Rename chat"
                        className="grid h-7 w-7 place-items-center rounded-full text-muted transition hover:text-primary"
                      >
                        <Pencil size={13} aria-hidden="true" />
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setActionError(null);
                          setEditing(null);
                          setConfirmingId(item.id);
                        }}
                        aria-label={`Delete chat: ${item.title}`}
                        title="Delete chat"
                        className="grid h-7 w-7 place-items-center rounded-full text-muted transition hover:text-negative"
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}

        {actionError && <p className="px-1 pt-3 text-[13.5px] text-negative">{actionError}</p>}

        {failed && (
          <p className="px-1 pt-3 text-[13.5px] text-negative">Could not load your chats. Is the backend running?</p>
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
