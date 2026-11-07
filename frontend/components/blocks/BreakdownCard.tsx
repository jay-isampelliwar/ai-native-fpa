import { PieChart } from 'lucide-react';

import type { BreakdownBlock } from '@/lib/types';
import { Dot, ShareBar, TileHead, colourAt } from '@/components/blocks/Tile';

/**
 * A `breakdown` block: groups of rows, each a colour dot, a label, a share bar and the share on
 * the right. Every row in a group is a share of one whole, so the bars share one scale.
 */
export default function BreakdownCard({ block }: { block: BreakdownBlock }) {
  return (
    <div className="min-w-0">
      {(block.title || block.subtitle) && <TileHead title={block.title ?? ''} subtitle={block.subtitle} icon={PieChart} />}

      <div className={`grid gap-x-8 gap-y-5 sm:grid-cols-2 ${block.title || block.subtitle ? 'mt-2' : ''}`}>
        {block.groups.map((group) => (
          <section key={group.title} aria-label={group.title} className="min-w-0">
            <h5 className="mb-1 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-muted">{group.title}</h5>

            <ul>
              {group.items.map((item, index) => {
                const pct = Math.max(0, Math.min(100, item.pct));
                const colour = colourAt(index);

                return (
                  <li key={item.label} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-t border-line py-2.5 first:border-t-0">
                    <Dot colour={colour} />
                    <div className="min-w-0">
                      <div className="truncate text-[14px] font-medium text-primary">{item.label}</div>
                      <ShareBar pct={pct} colour={colour} />
                    </div>
                    <span className="text-[14px] font-semibold tabular-nums text-primary">{item.value}</span>
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
