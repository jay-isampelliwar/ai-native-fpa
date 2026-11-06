import type { TableBlock } from '@/lib/types';

/**
 * A `table` block: plain column names, numbers on the right, scrolling sideways on a narrow screen.
 *
 * The table sits straight on the card with no frame of its own. Rows are split by hairlines and the
 * header is a muted line, so the card is the only box. It bleeds to the card's edges, so a wide
 * table scrolls the full width instead of inside an inset frame.
 */
export default function TableCard({ block }: { block: TableBlock }) {
  return (
    <div className="min-w-0">
      {(block.title || block.subtitle) && <BlockTitle title={block.title} subtitle={block.subtitle} />}

      <div className="quiet-scroll -mx-4 mt-2 -mb-2 overflow-x-auto sm:-mx-5">
        <table className="w-full border-collapse text-[14px] tabular-nums">
          <thead>
            <tr className="border-b border-line">
              {block.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={`px-4 pt-1 pb-2 text-[12.5px] font-medium whitespace-nowrap text-muted sm:px-5 ${
                    column.align === 'right' ? 'text-right' : 'text-left'
                  }`}
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {block.rows.map((row, index) => (
              <tr
                key={index}
                className="border-b border-line transition-colors last:border-b-0 hover:bg-[var(--hover-surface)]"
              >
                {block.columns.map((column, at) => (
                  <td
                    key={column.key}
                    className={`px-4 py-2.5 whitespace-nowrap sm:px-5 ${at === 0 ? 'font-medium text-primary' : 'text-primary'} ${
                      column.align === 'right' ? 'text-right' : 'text-left'
                    }`}
                  >
                    {row[column.key] ?? '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** The title and muted line at the top of a card or a part of one. */
export function BlockTitle({ title, subtitle }: { title?: string | null; subtitle?: string | null }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
      {title && <h4 className="text-[14.5px] font-semibold tracking-[-0.01em] text-primary">{title}</h4>}
      {subtitle && <p className="text-[12.5px] text-muted">{subtitle}</p>}
    </div>
  );
}
