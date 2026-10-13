'use client';

import { useEffect, useRef, useState } from 'react';

import { orbAnimation, paintFrame, type OrbState, type Tint } from '@/lib/orb/engine';

/**
 * A dotted orb drawn on a canvas, animated to show what the planner is doing.
 *
 * The dots are tinted with the theme's `--accent`, and the theme is read from `data-theme` on
 * `<html>`. Both are watched, so switching light and dark repaints at once. This works on the
 * sign-in page too, which sits outside the theme provider.
 *
 * The animation pauses when the orb is off screen or the tab is hidden. With reduced motion
 * turned on, or with `still`, it draws one frame and stops.
 */

const LABELS: Record<OrbState, string> = {
  working: 'Working…',
  searching: 'Searching…',
  solving: 'Solving…',
  listening: 'Listening…',
  connecting: 'Connecting…',
  weaving: 'Weaving…',
  composing: 'Composing…',
  breathing: 'Thinking…',
  shaping: 'Shaping…',
};

/** `#20c763` → { r, g, b }. Anything else gives no tint, so the dots fall back to grey. */
function parseHex(color: string): Tint | undefined {
  const hex = color.trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);

  if (!hex) return undefined;

  const full = hex[1].length === 3 ? hex[1].replace(/./g, (c) => c + c) : hex[1];
  const n = parseInt(full, 16);

  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

/** Whether the page is dark, and the accent colour, kept in step with `data-theme`. */
function useInk(): { dark: boolean; tint?: Tint } {
  const [ink, setInk] = useState<{ dark: boolean; tint?: Tint }>({ dark: true });

  useEffect(() => {
    const root = document.documentElement;

    const read = () =>
      setInk({
        dark: root.getAttribute('data-theme') !== 'light',
        tint: parseHex(getComputedStyle(root).getPropertyValue('--accent')),
      });

    read();

    const observer = new MutationObserver(read);
    observer.observe(root, { attributes: true, attributeFilter: ['data-theme'] });

    return () => observer.disconnect();
  }, []);

  return ink;
}

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const query = matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(query.matches);

    update();
    query.addEventListener('change', update);

    return () => query.removeEventListener('change', update);
  }, []);

  return reduced;
}

export default function ThinkingOrb({
  state = 'breathing',
  size = 64,
  still = false,
  label,
  className = '',
}: {
  state?: OrbState;
  size?: number;
  /** Draw one frame and stop. */
  still?: boolean;
  /** What a screen reader hears. Leave out when text next to the orb already says it. */
  label?: string;
  className?: string;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const { dark, tint } = useInk();
  const reduced = useReducedMotion();

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext('2d');

    if (!canvas || !ctx) return;

    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);

    const { speed, frame } = orbAnimation(state, size);

    const draw = (seconds: number) => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);
      paintFrame(ctx, frame(seconds * speed), dark, tint);
    };

    if (reduced || still) {
      draw(0.6);
      return;
    }

    let raf = 0;
    let running = false;
    let onScreen = true;

    const loop = () => {
      draw(performance.now() / 1000);
      if (running) raf = requestAnimationFrame(loop);
    };

    const start = () => {
      if (running || !onScreen || document.visibilityState === 'hidden') return;
      running = true;
      raf = requestAnimationFrame(loop);
    };

    const stop = () => {
      running = false;
      cancelAnimationFrame(raf);
    };

    draw(performance.now() / 1000);

    const observer = new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
      if (onScreen) start();
      else stop();
    });
    observer.observe(canvas);

    const onVisibility = () => (document.visibilityState === 'hidden' ? stop() : start());
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      stop();
      observer.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [state, size, still, reduced, dark, tint]);

  return (
    <canvas
      ref={ref}
      role={label === '' ? undefined : 'img'}
      aria-hidden={label === '' ? true : undefined}
      aria-label={label === '' ? undefined : (label ?? LABELS[state])}
      className={`block flex-none ${className}`}
      style={{ width: size, height: size }}
    />
  );
}
