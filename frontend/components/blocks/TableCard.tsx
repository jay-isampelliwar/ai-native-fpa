import type { TableBlock } from '@/lib/types';

/** A `table` block: plain column names, numbers on the right, scrolling sideways on a narrow screen. */
export default function TableCard({ block }: { block: TableBlock }) {
  return (
    <div className="min-w-0">
      {(block.title || block.subtitle) && <BlockTitle title={block.title} subtitle={block.subtitle} />}

      <div className="quiet-scroll overflow-x-auto rounded-xl border border-[var(--pane-border)]">
        <table className="w-full border-collapse text-[14px] tabular-nums">
          <thead>
            <tr>
              {block.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={`bg-panel-subtle px-3 py-2 font-semibold whitespace-nowrap text-secondary ${
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
              <tr key={index} className="border-t border-[var(--pane-border)] hover:bg-panel-subtle">
                {block.columns.map((column) => (
                  <td
                    key={column.key}
                    className={`px-3 py-2 whitespace-nowrap text-primary ${column.align === 'right' ? 'text-right' : 'text-left'}`}
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

/** The small title and muted line above a part of a card. */
export function BlockTitle({ title, subtitle }: { title?: string | null; subtitle?: string | null }) {
  return (
    <div className="mb-2 flex flex-wrap items-baseline gap-x-2">
      {title && <h4 className="text-[14.5px] font-semibold text-primary">{title}</h4>}
      {subtitle && <p className="text-[13px] text-muted">{subtitle}</p>}
    </div>
  );
}
