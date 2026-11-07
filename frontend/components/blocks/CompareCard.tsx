'use client';

import type { CompareBlock } from '@/lib/types';

/** Two things side by side: the measure's name sits in the middle between the two values. */
function TwoUp({ block }: { block: CompareBlock }) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-x-3.5 gap-y-2 text-[13.5px]">
      <span className="truncate text-right text-[14px] font-semibold text-primary">{block.columns[0]}</span>
      <span className="text-[11.5px] text-muted">vs</span>
      <span className="truncate text-[14px] font-semibold text-primary">{block.columns[1]}</span>
      <span className="col-span-3 border-t border-line" />

      {block.rows.map((row) => (
        <div key={row.label} className="contents">
          <span className={`truncate text-right tabular-nums ${row.best === 0 ? 'font-semibold text-positive' : 'text-primary'}`}>{row.values[0] ?? '—'}</span>
          <span className="text-center text-[11.5px] text-muted">{row.label}</span>
          <span className={`truncate tabular-nums ${row.best === 1 ? 'font-semibold text-positive' : 'text-primary'}`}>{row.values[1] ?? '—'}</span>
        </div>
      ))}
    </div>
  );
}

/** Three or four things side by side: the measure's name is the left column, the things are the headers. */
function ManyUp({ block }: { block: CompareBlock }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr>
            <th className="pb-2 text-left text-[11.5px] font-medium text-muted" scope="col">
              <span className="sr-only">Measure</span>
            </th>
            {block.columns.map((column) => (
              <th key={column} className="max-w-[140px] truncate pb-2 pl-3 text-right text-[13px] font-semibold text-primary" scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row) => (
            <tr key={row.label} className="border-t border-line">
              <th className="py-2 text-left text-[12px] font-normal text-muted" scope="row">
                {row.label}
              </th>
              {block.columns.map((column, index) => (
                <td key={column} className={`py-2 pl-3 text-right tabular-nums ${row.best === index ? 'font-semibold text-positive' : 'text-primary'}`}>
                  {row.values[index] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A `compare` block: two to four things side by side, one row per measure, the best value in each row in teal. */
export default function CompareCard({ block }: { block: CompareBlock }) {
  return (
    <div>
      {block.title && <div className="mb-3 text-[13px] font-semibold text-secondary">{block.title}</div>}

      {block.columns.length === 2 ? <TwoUp block={block} /> : <ManyUp block={block} />}

      {block.note && <p className="mt-3 border-t border-line pt-2.5 text-center text-[12.5px] text-muted">{block.note}</p>}
    </div>
  );
}
