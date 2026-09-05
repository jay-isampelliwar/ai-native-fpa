'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

import { alerts as alertsApi } from '@/lib/api';
import { readUserId, writeUserId } from '@/lib/session';

/**
 * The frame every page sits in — brand, the four places this goes, and who you are.
 *
 * Identity is resolved once here rather than per page. A user id present on one route and missing on
 * another would mean navigation could land somewhere that fetches with no identity, and that request
 * would either fail or, worse, succeed against a default and show someone else's money.
 *
 * Chat leads because it is what the product is. The other three exist because a conversation is the
 * wrong surface for typing in a salary, correcting an imported row, or scanning what needs attention
 * — that split is the product rule made navigable.
 *
 * Alerts is the only link that carries a count, because it is the only place the system speaks first.
 * Badging everything trains people to stop reading badges.
 *
 * The id reaches pages through context rather than a render prop. A function passed as `children`
 * cannot cross the server/client boundary - it is not serialisable into the RSC payload - so pages
 * stay server components and the client components inside them call `useUser`.
 */

const UserContext = createContext<number | null>(null);

/** The current user id. Only valid inside `Shell`, which does not render children without one. */
export function useUser(): number {
  const userId = useContext(UserContext);

  if (userId === null) {
    throw new Error('useUser was called outside Shell, which always provides a user id');
  }

  return userId;
}

const LINKS = [
  { href: '/', label: 'Chat' },
  { href: '/portfolio', label: 'Portfolio' },
  { href: '/import', label: 'Import' },
  { href: '/alerts', label: 'Alerts' },
] as const;

export default function Shell({ children }: { children: ReactNode }) {
  const [userId, setUserId] = useState<number | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setUserId(readUserId());
    setReady(true);
  }, []);

  if (!ready) return null;

  if (userId === null) return <Gate onChoose={setUserId} />;

  return (
    <UserContext.Provider value={userId}>
      <div className="ambient-grid" aria-hidden="true" />
      <Nav userId={userId} onSwitch={() => setUserId(null)} />
      <main className="relative z-10 flex min-h-0 w-full flex-1 flex-col">{children}</main>
    </UserContext.Provider>
  );
}

function Nav({ userId, onSwitch }: { userId: number; onSwitch: () => void }) {
  const pathname = usePathname();
  const [actionCount, setActionCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    alertsApi
      .list(userId)
      .then((response) => {
        if (!cancelled) setActionCount(response.action_required);
      })
      .catch(() => {
        if (!cancelled) setActionCount(0);
      });

    return () => {
      cancelled = true;
    };
  }, [userId, pathname]);

  return (
    <header className="relative z-20 border-b border-[#18312f]/8 bg-[#f5f2e8]/85 backdrop-blur">
      <nav className="mx-auto flex w-full max-w-[1180px] items-center gap-1 px-5 py-3">
        <Link href="/" className="mr-4 flex items-center gap-2.5">
          <span className="brand-mark" aria-hidden="true">
            <span />
          </span>
          <span className="font-serif text-[17px] leading-none tracking-[-0.01em] text-[#18312f]">
            Farline
          </span>
        </Link>

        {LINKS.map((link) => {
          const active = link.href === '/' ? pathname === '/' : pathname.startsWith(link.href);

          return (
            <Link
              key={link.href}
              href={link.href}
              className={`rounded-full px-3 py-1.5 text-[13px] transition ${
                active
                  ? 'bg-white/80 font-semibold text-[#18312f] shadow-[0_1px_3px_rgba(16,59,54,0.05)]'
                  : 'text-[#5d7470] hover:bg-white/50 hover:text-[#18312f]'
              }`}
            >
              {link.label}
              {link.href === '/alerts' && actionCount > 0 && (
                <span className="ml-1.5 rounded-full bg-[#b83f28] px-1.5 py-0.5 text-[10.5px] font-semibold text-white">
                  {actionCount}
                </span>
              )}
            </Link>
          );
        })}

        <button
          type="button"
          onClick={onSwitch}
          className="ml-auto flex items-center gap-2 text-[11.5px] text-[#8ba09c] transition hover:text-[#18312f]"
        >
          <span className="trust-dot" aria-hidden="true" />
          user {userId}
        </button>
      </nav>
    </header>
  );
}

/**
 * The blank state that asks who you are, because guessing would show someone else's money.
 *
 * This build identifies a caller by an integer with no credential behind it — a deliberate backend
 * decision while the planner itself is being proven. The honest interface for that is a field that
 * asks rather than a default that assumes.
 */
function Gate({ onChoose }: { onChoose: (userId: number) => void }) {
  const [draft, setDraft] = useState('');

  return (
    <>
      <div className="ambient-grid" aria-hidden="true" />

      <main className="relative z-10 flex flex-1 items-center justify-center px-5 py-16">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const parsed = Number(draft);
            if (Number.isInteger(parsed) && parsed > 0) {
              writeUserId(parsed);
              onChoose(parsed);
            }
          }}
          className="w-full max-w-[380px] rounded-2xl border border-[#18312f]/9 bg-white/80 p-7 shadow-[0_1px_3px_rgba(16,59,54,0.04)] backdrop-blur"
        >
          <span className="brand-mark" aria-hidden="true">
            <span />
          </span>

          <h1 className="mt-4 font-serif text-[26px] leading-[1.15] tracking-[-0.01em] text-[#18312f]">
            See the life your money can support
          </h1>

          <p className="mt-2 text-[13.5px] leading-6 text-[#4d6560]">
            This build identifies you by a user id. Sign-in comes later.
          </p>

          <input
            type="number"
            min={1}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="1"
            className="mt-5 w-full rounded-xl border border-[#18312f]/12 bg-white/90 px-3.5 py-2.5 text-[14px] text-[#18312f] outline-none transition placeholder:text-[#a8b8b4] focus:border-[#00947a]"
          />

          <button
            type="submit"
            disabled={!draft.trim()}
            className="mt-3 w-full rounded-xl bg-[#e7a14d] px-4 py-2.5 text-[13.5px] font-semibold text-[#18312f] transition hover:bg-[#dda044] disabled:cursor-not-allowed disabled:opacity-40"
          >
            Continue
          </button>
        </form>
      </main>
    </>
  );
}
