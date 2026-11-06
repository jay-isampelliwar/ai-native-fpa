'use client';

import { RotateCw } from 'lucide-react';
import { useEffect, useState } from 'react';

import Orb from '@/components/ui/Orb';
import { retrySession } from '@/lib/session';

/** How long the plain loading view shows before it says the server may be waking up. */
const SLOW_AFTER_MS = 3_000;

/**
 * What shows while the app learns who is signed in. A sleeping server can take most of a minute to
 * answer the first call, so after a few seconds it says so, and if the server never answers it
 * offers a retry instead of a blank page.
 */
export default function StartupScreen({ unreachable }: { unreachable: boolean }) {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);

    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-5 bg-background px-6 text-center" aria-busy={!unreachable}>
      <Orb size={56} />

      {unreachable ? (
        <div className="max-w-[34ch]">
          <p className="text-[15px] font-medium text-primary">Can&apos;t reach the server right now.</p>
          <p className="mt-1.5 text-[13.5px] text-muted">It may be starting up or down. Please try again.</p>
          <button
            type="button"
            onClick={() => void retrySession()}
            className="chip-button mx-auto mt-4 h-9 gap-1.5 px-4 text-[13.5px] font-medium"
          >
            <RotateCw size={14} aria-hidden="true" />
            Try again
          </button>
        </div>
      ) : (
        <p aria-live="polite" className={`max-w-[34ch] text-[13.5px] text-muted transition-opacity duration-300 ${slow ? 'opacity-100' : 'opacity-0'}`}>
          Starting up the server. This can take up to a minute.
        </p>
      )}
    </div>
  );
}
