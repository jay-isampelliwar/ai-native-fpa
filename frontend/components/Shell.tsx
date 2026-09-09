'use client';

import Link from 'next/link';
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';

import { users } from '@/lib/api';
import { clearUserId, readUserId, serverUserId, subscribeToUserId, writeUserId } from '@/lib/session';

/**
 * The frame the conversation sits in — brand, and who you are.
 *
 * Identity is resolved once here rather than per page. A user id present on one route and missing on
 * another would mean navigation could land somewhere that fetches with no identity, and that request
 * would either fail or, worse, succeed against a default and show someone else's money.
 *
 * There is no navigation, because there is nowhere else to go. The portfolio and alerts pages were
 * removed with the endpoints behind them, and the count of findings that used to sit in this bar went
 * with them. What is left is the mark, and the one control that is genuinely about the frame rather
 * than the conversation: which person's records are on screen.
 *
 * The id is registered with the backend on every visit, not just when it is first typed. Identity here
 * is an integer a person chose, kept in this browser, and nothing else told the server that the person
 * exists — so every table's foreign key pointed at a row nobody had created, and the failure surfaced
 * at whatever first tried to write. Registering costs one idempotent call and moves that failure out
 * of existence rather than earlier.
 *
 * The id reaches pages through context rather than a render prop. A function passed as `children`
 * cannot cross the server/client boundary - it is not serialisable into the RSC payload - so pages
 * stay server components and the client components inside them call `useUser`.
 *
 * Identity is subscribed to rather than copied into state on mount. Local storage does not exist on
 * the server, so the first render has to be told there is no answer yet - `undefined`, distinct from
 * `null`, which is a real answer meaning nobody is signed in. Rendering nothing for that one pass is
 * what stops the sign-in card appearing for a frame in front of someone who is already signed in.
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

export default function Shell({ children }: { children: ReactNode }) {
  const userId = useSyncExternalStore(subscribeToUserId, readUserId, serverUserId);

  // Every visit, not only the first: the id lives in this browser, so this is the only moment the
  // backend can learn that the person holding it exists.
  useEffect(() => {
    if (typeof userId !== 'number') return;

    void users.register(userId).catch(() => {
      // A backend that cannot be reached is reported by whatever the person does next, which will
      // fail visibly and say so. Failing here would only replace the app with a blank screen.
    });
  }, [userId]);

  if (userId === undefined) return null;

  if (userId === null) return <Gate />;

  return (
    <UserContext.Provider value={userId}>
      <div className="ambient-grid" aria-hidden="true" />
      <Nav userId={userId} onSwitch={clearUserId} />
      <main className="relative z-10 flex min-h-0 w-full flex-1 flex-col">{children}</main>
    </UserContext.Provider>
  );
}

function Nav({ userId, onSwitch }: { userId: number; onSwitch: () => void }) {
  return (
    <header className="relative z-20 border-b border-[#18312f]/8 bg-[#f5f2e8]/85 backdrop-blur">
      <nav className="mx-auto flex w-full max-w-[1180px] items-center px-5 py-3">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="brand-mark" aria-hidden="true">
            <span />
          </span>
          <span className="font-serif text-[17px] leading-none tracking-[-0.01em] text-[#18312f]">
            Farline
          </span>
        </Link>

        <button
          type="button"
          onClick={onSwitch}
          title="Switch to another user id"
          className="ml-auto flex items-center gap-2 rounded-full px-2.5 py-1.5 text-[11.5px] text-[#8ba09c] transition hover:bg-white/60 hover:text-[#18312f]"
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
 *
 * Writing the id is the whole of submitting. The store announces the change and `Shell` re-reads it,
 * so there is no second copy of the answer to keep in step with the one in storage.
 */
function Gate() {
  const [draft, setDraft] = useState('');

  return (
    <>
      <div className="ambient-grid" aria-hidden="true" />

      <main className="relative z-10 flex flex-1 items-center justify-center px-5 py-16">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const parsed = Number(draft);
            if (Number.isInteger(parsed) && parsed > 0) writeUserId(parsed);
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
