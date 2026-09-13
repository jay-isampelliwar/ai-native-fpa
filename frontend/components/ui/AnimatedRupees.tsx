'use client';

import { groupedDigits, rupeesShort } from '@/lib/format';
import { useCountUp } from '@/lib/useCountUp';

/**
 * A rupee total that travels to its new value rather than jumping to it.
 *
 * The grouping is re-applied on every frame, so the digits stay in lakh/crore
 * groups the whole way across instead of becoming an ungrouped run of numerals
 * mid-animation. That is the doc's requirement and it is also the only version
 * that does not look broken.
 *
 * The accessible text is the settled figure, not the frame currently painted. A
 * screen reader announcing a number counting up would read a dozen wrong values
 * before the right one.
 */
export default function AnimatedRupees({
  value,
  short = false,
  className = '',
}: {
  value: number;
  /** `₹48.5L` rather than `₹48,49,000`, for headline positions with no room. */
  short?: boolean;
  className?: string;
}) {
  const display = useCountUp(value);

  const settled = short ? rupeesShort(value) : `₹${groupedDigits(value)}`;
  const painting = short ? rupeesShort(display) : `₹${groupedDigits(display)}`;

  return (
    <span className={`tabular ${className}`}>
      <span aria-hidden="true">{painting}</span>
      <span className="sr-only">{settled}</span>
    </span>
  );
}
