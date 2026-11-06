import type { BreakdownBlock } from '@/lib/types';
import { BlockTitle } from '@/components/blocks/TableCard';

/** A `breakdown` block: groups of labelled bars, such as an investment mix by asset class and by sector. */
export default function BreakdownCard({ block }: { block: BreakdownBlock }) {
  return (
    <div className="min-w-0">
      {(block.title || block.subtitle) && <BlockTitle title={block.title} subtitle={block.subtitle} />}

      <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        {block.groups.map((group) => (
          <section key={group.title} aria-label={group.title} className="min-w-0">
            <h5 className="mb-2 text-[13px] font-semibold tracking-wide text-muted uppercase">{group.title}</h5>

            <ul className="space-y-2">
              {group.items.map((item) => (
                <li key={item.label}>
                  <div className="flex items-baseline justify-between gap-3 text-[14px]">
                    <span className="truncate text-primary">{item.label}</span>
                    <span className="flex-none tabular-nums text-secondary">{item.value}</span>
                  </div>

                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--track)]">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${Math.max(0, Math.min(100, item.pct))}%`, background: 'var(--accent)' }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
