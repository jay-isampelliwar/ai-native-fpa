'use client';

import { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from 'framer-motion';

/**
 * Walk a displayed figure from the value it was showing to the value it now is.
 *
 * The doc is specific about two things here, and both are about not lying to the
 * reader. A number must never animate from zero when it is being updated — the
 * portfolio was not worth nothing a moment ago — so the animation starts from
 * whatever was last on screen, held in a ref rather than derived from the props.
 * And the first render does not animate at all: there is no previous value to
 * come from, so the figure simply is what it is.
 *
 * A reader who asked for reduced motion gets the final value immediately. Not a
 * faster count — no count, because the effect being removed is the motion itself.
 */
export function useCountUp(target: number, durationMs = 520): number {
  const reduced = useReducedMotion();

  const [display, setDisplay] = useState(target);
  const from = useRef(target);
  const first = useRef(true);

  useEffect(() => {
    // Nothing to travel from on the first pass, and nothing to travel to if the
    // figure has not moved.
    if (first.current) {
      first.current = false;
      from.current = target;
      setDisplay(target);
      return;
    }

    if (reduced || from.current === target) {
      from.current = target;
      setDisplay(target);
      return;
    }

    const start = performance.now();
    const origin = from.current;
    const distance = target - origin;

    let frame = 0;

    function step(now: number) {
      const progress = Math.min(1, (now - start) / durationMs);

      // Ease out: the figure arrives gently rather than stopping dead.
      const eased = 1 - Math.pow(1 - progress, 3);

      setDisplay(origin + distance * eased);

      if (progress < 1) {
        frame = requestAnimationFrame(step);
      } else {
        from.current = target;
      }
    }

    frame = requestAnimationFrame(step);

    return () => {
      cancelAnimationFrame(frame);
      // Whatever was on screen when this was interrupted is where the next
      // animation must start, or a fast sequence of changes jumps.
      from.current = display;
    };
    // `display` is deliberately not a dependency: it changes every frame, and
    // reading it in cleanup is the only use it has here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs, reduced]);

  return display;
}
