'use client';

import { Check, LogOut, UserRound } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { PROFILE } from '@/lib/mock/data';
import { writeUserId } from '@/lib/session';

/**
 * The avatar, and the one thing behind it that is real: which user id is in use.
 *
 * This build has no accounts. A caller is an integer with no credential behind it,
 * which is a deliberate backend decision while the planner is being proven. So the
 * honest menu here is not "sign out" — there is no session to end — but "these
 * records belong to user N, and you can look at a different N".
 *
 * The name and initials above it are mock, and the menu says so rather than
 * implying the backend knows who Rohan is.
 *
 * Switching writes to the session store and nothing else. Everything that depends
 * on identity is remounted by the shell when the id changes, so this component does
 * not have to know what those things are or reset any of them.
 */
export default function UserMenu({ userId }: { userId: number | null }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');

  const root = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }

    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }

    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKey);

    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  // Opening should put the caret in the field, so switching is type-and-enter.
  useEffect(() => {
    if (open) field.current?.focus();
  }, [open]);

  function submit(event: React.FormEvent) {
    event.preventDefault();

    const parsed = Number(draft);

    if (!Number.isInteger(parsed) || parsed <= 0 || parsed === userId) return;

    writeUserId(parsed);
    setOpen(false);
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => {
          if (!open) setDraft(userId ? String(userId) : '');
          setOpen((current) => !current);
        }}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`Account. Currently user ${userId ?? 'unknown'}. Open menu`}
        title={`User ${userId ?? '—'}`}
        className="ml-1 grid h-8 w-8 flex-none place-items-center rounded-full text-[11.5px] font-bold transition hover:opacity-85"
        style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
      >
        {PROFILE.initials}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Account"
          className="absolute right-0 z-50 mt-1.5 w-64 rounded-xl border border-line bg-panel-elevated p-3 shadow-[var(--shadow-card)]"
        >
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="grid h-9 w-9 flex-none place-items-center rounded-full text-[12px] font-bold"
              style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
            >
              {PROFILE.initials}
            </span>

            <div className="min-w-0">
              <p className="truncate text-[13px] font-semibold text-primary">{PROFILE.name}</p>
              <p className="tabular truncate text-[11.5px] text-muted">User id {userId ?? '—'}</p>
            </div>
          </div>

          {/* Said plainly, because a menu that looks like an account menu and is not
              one will be trusted as though it were. */}
          <p className="mt-3 rounded-lg bg-panel-subtle px-2.5 py-2 text-[11px] leading-[1.45] text-secondary">
            This build has no sign-in. The name above is placeholder; the id below is
            what the planner actually reads your records with.
          </p>

          <form onSubmit={submit} className="mt-3">
            <label
              htmlFor="switch-user"
              className="mb-1.5 block text-[11px] font-medium text-secondary"
            >
              Switch to another user id
            </label>

            <div className="flex items-center gap-1.5">
              <span className="relative flex-1">
                <UserRound
                  size={13}
                  aria-hidden="true"
                  className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted"
                />
                <input
                  id="switch-user"
                  ref={field}
                  type="number"
                  min={1}
                  inputMode="numeric"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="1"
                  className="num-field tabular w-full rounded-lg border border-line bg-panel py-2 pr-2.5 pl-7 text-[13px] text-primary transition focus:border-accent"
                />
              </span>

              <button
                type="submit"
                disabled={!draft.trim() || Number(draft) === userId}
                aria-label="Switch user"
                className="grid h-[34px] w-[34px] flex-none place-items-center rounded-lg transition disabled:cursor-not-allowed disabled:opacity-40"
                style={{ background: 'var(--accent)', color: 'var(--on-accent)' }}
              >
                <Check size={15} strokeWidth={2.6} aria-hidden="true" />
              </button>
            </div>

            <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-[1.4] text-muted">
              <LogOut size={11} className="mt-0.5 flex-none" aria-hidden="true" />
              Switching starts a new conversation. The dashboard is demo data and does
              not change.
            </p>
          </form>
        </div>
      )}
    </div>
  );
}
