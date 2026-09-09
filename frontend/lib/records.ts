'use client';

import { useEffect, useState } from 'react';

/**
 * The one signal that says a person's records moved, and the one way to listen for it.
 *
 * Nothing in this app stores a derived figure. The backend computes cash flow, goal projections,
 * portfolio totals and alerts at read time, every time, so "recalculate" is never a cache to
 * invalidate — it is a fetch. What the client needs is therefore not a synchronisation layer but an
 * answer to one question: when is it worth fetching again?
 *
 * The answer is when something wrote. That moment is known precisely — an import committed — and it
 * is known only by the component that did it, so that component says so and everything reading
 * records listens. A timer would either lag the change or ask a question nobody
 * needed answered every few seconds, against figures that had not moved since the last time it asked.
 *
 * This lived inside `ChatPanel` before, with the event name written out in two files and the listener
 * hand-rolled in each. That was fine while the chat and the header were the only things that cared,
 * and it stopped being fine the moment the workspace panel, the portfolio page and the alerts page all
 * wanted the same signal: four subscribers to an event whose name was a string literal in whichever
 * file happened to need it. One name, declared once, is the whole reason this file exists.
 *
 * `useRecordsVersion` returns a counter rather than firing a callback. A counter drops straight into a
 * `useEffect` dependency array, which is where nearly every caller wants it, and it makes the refetch
 * follow exactly the same path on a change as it does on mount — so there is no second code path that
 * can be subtly wrong.
 *
 * The scope is deliberately this tab. A change made in another tab or on another device will not
 * refresh this one, because reaching those needs a poll or a stream and neither is worth the
 * complexity for a single person moving through one window. What this does guarantee is that nothing
 * *this* tab changed is ever left stale on screen beside the thing that changed it.
 */

const RECORDS_CHANGED = 'records-changed';

/** Announce that something just wrote to this person's records, so every reader refetches. */
export function announceRecordsChanged(): void {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(new Event(RECORDS_CHANGED));
}

/** A counter that increments whenever the records change, for use as a refetch dependency. */
export function useRecordsVersion(): number {
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const bump = () => setVersion((current) => current + 1);

    window.addEventListener(RECORDS_CHANGED, bump);

    return () => window.removeEventListener(RECORDS_CHANGED, bump);
  }, []);

  return version;
}
