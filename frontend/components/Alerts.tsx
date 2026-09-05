'use client';

import { useEffect, useState } from 'react';

import { useUser } from '@/components/Shell';
import { alerts as alertsApi } from '@/lib/api';
import type { Alert } from '@/lib/types';

/**
 * What the planner noticed without being asked.
 *
 * These are computed on request, never stored. A stored alert goes stale the moment a record changes,
 * and telling someone their goal is drifting after they have already fixed it costs more trust than
 * saying nothing — so this screen is always as current as the records behind it.
 *
 * Severity orders the list, because an unprompted claim about someone's money should lead with what
 * needs a decision rather than what is merely worth knowing. An action is something that happens
 * whether or not you choose; attention is something worth seeing.
 *
 * Every alert shows the records and the calculator version behind it. A finding nobody asked for
 * should be at least as traceable as an answer they did — arguably more, since they did not invite it.
 */

const SEVERITY: Record<Alert['severity'], { label: string; dot: string; chip: string }> = {
  action: {
    label: 'Needs a decision',
    dot: 'bg-[#b83f28]',
    chip: 'border-[#b83f28]/28 bg-[#b83f28]/8 text-[#8f4227]',
  },
  attention: {
    label: 'Worth knowing',
    dot: 'bg-[#bf8410]',
    chip: 'border-[#bf8410]/28 bg-[#bf8410]/8 text-[#8a5a12]',
  },
  info: {
    label: 'Context',
    dot: 'bg-[#8ba09c]',
    chip: 'border-[#18312f]/12 bg-[#f5f2e8]/70 text-[#5d7470]',
  },
};

export default function Alerts() {
  const userId = useUser();

  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    alertsApi
      .list(userId)
      .then((response) => {
        if (!cancelled) setAlerts(response.alerts);
      })
      .catch(() => {
        if (!cancelled) setError('Alerts could not be loaded.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [userId]);

  return (
    <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[760px] space-y-5 px-5 py-7">
        <header>
          <h1 className="font-serif text-[28px] leading-[1.15] tracking-[-0.015em] text-[#18312f]">
            What I noticed
          </h1>

          <p className="mt-1.5 max-w-[52ch] text-[13px] leading-5 text-[#4d6560]">
            Worked out from your records just now, not saved from earlier.
          </p>
        </header>

        {loading && <p className="text-[13px] text-[#a8b8b4]">Checking your position…</p>}

        {error && (
          <div className="rounded-xl border border-[#c2603f]/25 bg-[#c2603f]/8 px-3.5 py-2.5 text-[12.5px] leading-5 text-[#8f4227]">
            {error}
          </div>
        )}

        {!loading && !error && alerts.length === 0 && (
          <div className="rounded-2xl border border-[#00947a]/25 bg-[#00947a]/8 px-5 py-4">
            <p className="text-[13.5px] leading-6 text-[#0f5f50]">
              Nothing needs your attention. Your committed outflow is within your income and no goal has
              drifted out of reach.
            </p>
          </div>
        )}

        <ul className="space-y-3">
          {alerts.map((alert, index) => {
            const severity = SEVERITY[alert.severity];

            return (
              <li
                key={`${alert.kind}-${index}`}
                className="rounded-2xl border border-[#18312f]/9 bg-white/80 px-5 py-4 shadow-[0_1px_3px_rgba(16,59,54,0.04)]"
              >
                <div className="flex items-start gap-3">
                  <span
                    aria-hidden="true"
                    className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${severity.dot}`}
                  />

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <h2 className="text-[14px] font-semibold leading-5 text-[#18312f]">
                        {alert.title}
                      </h2>

                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10.5px] font-medium ${severity.chip}`}
                      >
                        {severity.label}
                      </span>
                    </div>

                    <p className="mt-1.5 text-[13px] leading-[1.6] text-[#4d6560]">{alert.detail}</p>

                    {(alert.evidence_ids.length > 0 || alert.calculator_versions.length > 0) && (
                      <p className="mt-2.5 text-[11px] leading-4 text-[#a8b8b4]">
                        {alert.evidence_ids.length > 0 && (
                          <>
                            from {alert.evidence_ids.length} record
                            {alert.evidence_ids.length === 1 ? '' : 's'}
                          </>
                        )}
                        {alert.calculator_versions.length > 0 && (
                          <> · {alert.calculator_versions.join(', ')}</>
                        )}
                      </p>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
