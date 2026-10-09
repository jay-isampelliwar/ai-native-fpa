'use client';

import { Bar, ComposedChart, Line, ReferenceDot, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts';

/**
 * A small line with faint bars behind it, as on the reference's rate cards.
 *
 * The bars are the same values as the line, drawn thin and pale, so the card gets
 * its texture from the data rather than from a decoration.
 *
 * `mark` picks one point to call out with a dot and a dashed drop line, which is how
 * the side cards show where their month sits in the run of months around it.
 *
 * The scale is padded around the data, not anchored at zero, so a figure that moves
 * a few percent still shows a shape.
 */
export default function Sparkline({
  values,
  color,
  height = 56,
  bars = true,
  mark,
}: {
  values: number[];
  color: string;
  height?: number;
  bars?: boolean;
  mark?: number;
}) {
  const data = values.map((value, at) => ({ at, value }));

  const low = Math.min(...values);
  const high = Math.max(...values);
  const spread = high - low || Math.max(1, high * 0.1);
  const floor = low - spread * 0.6;

  const marked = mark !== undefined ? data[mark] : undefined;

  return (
    <div style={{ height }} className="w-full" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 6, right: 6, bottom: 2, left: 6 }}>
          <XAxis dataKey="at" hide />
          <YAxis hide domain={[floor, high + spread * 0.25]} />

          {bars && (
            <Bar dataKey="value" fill={color} fillOpacity={0.14} barSize={3} isAnimationActive={false} />
          )}

          {marked && (
            <ReferenceLine x={marked.at} stroke={color} strokeDasharray="2 3" strokeOpacity={0.7} />
          )}

          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            dot={marked ? false : { r: 2.5, fill: 'var(--panel)', stroke: color, strokeWidth: 1.5 }}
            isAnimationActive={false}
          />

          {marked && (
            <ReferenceDot x={marked.at} y={marked.value} r={4} fill="var(--panel)" stroke={color} strokeWidth={2} />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
