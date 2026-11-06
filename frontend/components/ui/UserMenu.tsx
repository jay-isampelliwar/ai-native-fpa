'use client';

import { LoaderCircle, LogOut } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { initialsOf } from '@/lib/format';
import { signOut, useSession } from '@/lib/session';

/**
 * The avatar, and behind it the signed-in person's name, email and a sign-out button.
 *
 * Signing out clears the cookie on the backend and the user in the session store,
 * then sends the page to `/signin`.
 */
export default function UserMenu() {
  const router = useRouter();
  const session = useSession();

  const [open, setOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const root = useRef<HTMLDivElement>(null);

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

  if (session.status !== 'signed-in') return null;

  const { user } = session;
  const initials = initialsOf(user.name);

  async function leave() {
    setLeaving(true);

    await signOut();

    router.replace('/signin');
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`Account for ${user.name}. Open menu`}
        title={user.name}
        className="grid h-8 w-8 flex-none place-items-center rounded-full text-[13px] font-bold transition hover:opacity-85"
        style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
      >
        {initials}
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
              className="grid h-9 w-9 flex-none place-items-center rounded-full text-[13.5px] font-bold"
              style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
            >
              {initials}
            </span>

            <div className="min-w-0">
              <p className="truncate text-[14.5px] font-semibold text-primary">{user.name}</p>
              <p className="truncate text-[13px] text-muted">{user.email}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={leave}
            disabled={leaving}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-line py-2 text-[14.5px] font-medium text-primary transition hover:bg-panel-subtle disabled:opacity-60"
          >
            {leaving ? (
              <LoaderCircle size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <LogOut size={14} aria-hidden="true" />
            )}
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
