'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { Card } from '@/components/blocks';
import { ImportSummary, Mapping, Reconcile } from '@/components/import-parts';
import { useUser } from '@/components/Shell';
import { documents } from '@/lib/api';
import type { ImportRead, StagedRow, StagedRowsPage } from '@/lib/types';

/**
 * One import, living inside the turn that started it.
 *
 * A file dropped into the conversation is a question — "what is in this?" — and the answer belongs
 * where the question was asked. So this owns the whole lifecycle of a single upload and redraws in
 * place as it moves: reading, then what was read, then a mapping if the layout is new, then the rows
 * awaiting a decision, then what was written. The turn above it never changes and the turn below it
 * never moves, which is what makes a conversation readable while something in it is still working.
 *
 * The upload fires once, guarded by a ref rather than by an empty dependency array alone. Strict mode
 * mounts every effect twice in development, and an unguarded upload would send the same statement
 * twice — harmless only because the backend happens to deduplicate, which is not a thing to rely on.
 *
 * Extraction outlives the request that started it, so this polls the import's status. The poll is a
 * loop rather than a function that re-schedules itself: it reads as the sequence it is, it cannot be
 * called from anywhere but the effect that owns it, and one cancelled flag stops every await in it.
 * Stopping matters — a chat holds many of these at once, and a turn scrolled out of view that keeps
 * asking the backend how it is doing is a leak with a network bill.
 *
 * Committing does not remove the turn. What a file added is part of the record of the conversation,
 * and a card that vanishes on success leaves a person unable to answer "which upload did that?".
 */

const POLL_MS = 700;

type Props = {
  file: File;
  onCommitted?: (summary: string) => void;
};

export default function ImportTurn({ file, onCommitted }: Props) {
  const userId = useUser();

  const [record, setRecord] = useState<ImportRead | null>(null);
  const [rows, setRows] = useState<StagedRowsPage | null>(null);
  const [progress, setProgress] = useState<string | null>(`Reading ${file.name}`);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const started = useRef(false);
  const alive = useRef(true);

  const loadRows = useCallback(
    async (importId: string) => {
      const page = await documents.rows(userId, importId);
      if (alive.current) setRows(page);
    },
    [userId],
  );

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    let cancelled = false;

    (async () => {
      try {
        let current = await documents.upload(userId, file);

        if (cancelled) return;

        setRecord(current);

        while (current.status === 'uploaded' || current.status === 'extracting') {
          await wait(POLL_MS);

          if (cancelled) return;

          current = await documents.read(userId, current.id);

          if (cancelled) return;

          setRecord(current);
        }

        setProgress(null);

        if (current.status === 'extracted') {
          const page = await documents.rows(userId, current.id);

          if (!cancelled) setRows(page);
        }
      } catch {
        if (cancelled) return;

        setError('That file could not be read. Spreadsheets and bank CSVs are what this understands.');
        setProgress(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [userId, file]);

  useEffect(() => {
    return () => {
      alive.current = false;
    };
  }, []);

  async function decideAll(status: 'accepted' | 'rejected') {
    if (!record) return;
    setRows(await documents.decideAll(userId, record.id, status, true));
  }

  async function decideRow(row: StagedRow, status: 'accepted' | 'rejected') {
    if (!record) return;
    await documents.decideRow(userId, record.id, row.id, status);
    await loadRows(record.id);
  }

  async function commit() {
    if (!record) return;

    setBusy(true);

    try {
      const outcome = await documents.commit(userId, record.id);

      if (outcome.status === 'committed') {
        setRecord(await documents.read(userId, record.id));
        setRows(null);
        onCommitted?.(
          `${outcome.rows_written} record${outcome.rows_written === 1 ? '' : 's'} from ${file.name}`,
        );
      } else {
        setError(outcome.detail ?? `Nothing was committed (${outcome.status}).`);
      }
    } catch {
      setError('The commit did not go through. Nothing was written.');
    } finally {
      setBusy(false);
    }
  }

  if (progress) {
    return (
      <Card>
        <div className="flex items-center gap-2.5">
          <Spinner />
          <span className="text-[12.5px] font-medium leading-4 text-[#0f5f50]">{progress}</span>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {error && (
        <div className="rounded-xl border border-[#c2603f]/25 bg-[#c2603f]/8 px-3.5 py-2.5 text-[12.5px] leading-5 text-[#8f4227]">
          {error}
        </div>
      )}

      {record && <ImportSummary record={record} />}

      {record?.status === 'needs_mapping' && (
        <Mapping
          userId={userId}
          importId={record.id}
          onConfirmed={async (updated) => {
            setRecord(updated);
            if (updated.status === 'extracted') await loadRows(updated.id);
          }}
        />
      )}

      {record?.status === 'extracted' && rows && (
        <Reconcile
          rows={rows}
          busy={busy}
          onDecideAll={decideAll}
          onDecideRow={decideRow}
          onCommit={commit}
        />
      )}
    </div>
  );
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function Spinner() {
  return (
    <svg className="h-4 w-4 shrink-0 animate-spin text-[#00947a]" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" fill="none" />
      <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}
