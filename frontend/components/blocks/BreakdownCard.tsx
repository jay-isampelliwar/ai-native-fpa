import type { BreakdownBlock } from '@/lib/types';
import { BlockTitle } from '@/components/blocks/TableCard';

/**
 * A `breakdown` block: groups of labelled bars, such as an investment mix by asset class and by sector.
 *
 * Each bar is a share of one whole, so all bars in the card use the one neutral meter colour; a hue
 * per row would suggest the rows are different kinds of thing. Groups sit side by side on a wide
 * screen, split by space, not by boxes.
 */
export default function BreakdownCard({ block }: { block: BreakdownBlock }) {
  return (
    <div className="min-w-0">
      {(block.title || block.subtitle) && <BlockTitle title={block.title} subtitle={block.subtitle} />}

      <div className="mt-3 grid gap-x-8 gap-y-5 sm:grid-cols-2">
        {block.groups.map((group) => (
          <section key={group.title} aria-label={group.title} className="min-w-0">
            <h5 className="card-label mb-2.5 font-medium">{group.title}</h5>

            <ul className="space-y-3">
              {group.items.map((item) => {
                const pct = Math.max(0, Math.min(100, item.pct));

                return (
                  <li key={item.label}>
                    <div className="flex items-baseline justify-between gap-3 text-[14px]">
                      <span className="truncate text-primary">{item.label}</span>
                      <span className="flex-none tabular-nums text-secondary">{item.value}</span>
                    </div>

                    <div className="meter mt-1.5" aria-hidden="true">
                      <span style={{ width: `${pct}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
