'use client';

import { useEffect, useRef, type RefObject } from 'react';

const BARS = 5;
const MIN_HEIGHT = 3;
const MAX_HEIGHT = 16;

/**
 * Five bars that move with the person's voice while the microphone is open. They read the
 * analyser straight from the audio graph on every frame, so no React state changes per frame.
 * With reduced motion the bars stay still at a middle height.
 */
export default function VoiceBars({ analyser }: { analyser: RefObject<AnalyserNode | null> }) {
  const bars = useRef<(HTMLSpanElement | null)[]>([]);

  useEffect(() => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    let frame = 0;
    let bins: Uint8Array<ArrayBuffer> | null = null;

    const draw = () => {
      const node = analyser.current;

      if (node) {
        if (!bins || bins.length !== node.frequencyBinCount) bins = new Uint8Array(node.frequencyBinCount);

        node.getByteFrequencyData(bins);

        // Voice lives in the lower bins; each bar takes the average of its own slice of them.
        const used = Math.max(BARS, Math.floor(bins.length * 0.4));
        const slice = Math.floor(used / BARS);

        for (let i = 0; i < BARS; i += 1) {
          let sum = 0;
          for (let j = i * slice; j < (i + 1) * slice; j += 1) sum += bins[j];

          const level = Math.min(1, (sum / slice / 255) * 3);
          const bar = bars.current[i];

          if (bar) bar.style.height = `${MIN_HEIGHT + level * (MAX_HEIGHT - MIN_HEIGHT)}px`;
        }
      }

      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);

    return () => cancelAnimationFrame(frame);
  }, [analyser]);

  return (
    <span aria-hidden className="flex h-4 items-center gap-[2px]">
      {Array.from({ length: BARS }, (_, i) => (
        <span
          key={i}
          ref={(el) => {
            bars.current[i] = el;
          }}
          className="w-[3px] rounded-full bg-current transition-[height] duration-75 ease-out"
          style={{ height: `${MIN_HEIGHT + 4}px` }}
        />
      ))}
    </span>
  );
}
