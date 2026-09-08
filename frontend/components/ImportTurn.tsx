'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { Card } from '@/components/blocks';
import { ImportSummary, Mapping, Reconcile } from '@/components/import-parts';
import { useUser } from '@/components/Shell';
import { ApiError, documents } from '@/lib/api';
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
 * That guard needs the liveness flag to be a ref that the mount re-arms, and getting this wrong hung
 * every import in the chat. A per-run `let cancelled` is set by strict mode's immediate cleanup, and
 * the remount that follows hits the ref guard and starts nothing — so the one run in flight discarded
 * its own result, `progress` kept its initial value, and a spinner sat over an import the backend had
 * already finished. The two facts have to agree: if the guard survives the remount then so must the
 * run it belongs to, which is what re-arming `alive` at the top of the effect does.
 *
 * Extraction outlives the request that started it, so this polls the import's status. The poll is a
 * loop rather than a function that re-schedules itself: it reads as the sequence it is, it cannot be
 * called from anywhere but the effect that owns it, and one liveness ref stops every await in it.
 * Stopping matters — a chat holds many of these at once, and a turn scrolled out of view that keeps
 * asking the backend how it is doing is a leak with a network bill.
 *
 * The mapping form is opened by the person, not by the file. Every workbook is now read on arrival -
 * see `app/extraction/sheets.py` - so the normal path is rows to review, and the form exists for the
 * case where a column was read wrongly. It still appears on its own when a reading was impossible,
 * because then there is nothing else to offer.
 *
 * Committing does not remove the turn. What a file added is part of the record of the conversation,
 * and a card that vanishes on success leaves a person unable to answer "which upload did that?".
 *
 * The commit reports which failure it hit, and no longer treats the refresh that follows it as part
 * of the write. One `try` around both meant a 404, a server error, an unreachable backend and a
 * failed re-read all printed "Nothing was written" — true for three of them and a lie about the
 * fourth, which is the one where the rows are already on disk. The status the client already holds
 * is the difference between "press it again" and "this will never work".
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
  const [remapping, setRemapping] = useState(false);

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
    // Re-armed before the guard returns: strict mode's cleanup stops this turn a moment after it
    // starts, and the run it stopped is the only one there will ever be.
    alive.current = true;

    if (started.current) return;
    started.current = true;

    (async () => {
      try {
        let current = await documents.upload(userId, file);

        if (!alive.current) return;

        setRecord(current);

        while (current.status === 'uploaded' || current.status === 'extracting') {
          await wait(POLL_MS);

          if (!alive.current) return;

          current = await documents.read(userId, current.id);

          if (!alive.current) return;

          setRecord(current);
        }

        setProgress(null);

        if (current.status === 'extracted') {
          const page = await documents.rows(userId, current.id);

          if (alive.current) setRows(page);
        }
      } catch {
        if (!alive.current) return;

        setError('That file could not be read. Spreadsheets and bank CSVs are what this understands.');
        setProgress(null);
      }
    })();

    return () => {
      alive.current = false;
    };
  }, [userId, file]);

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
    setError(null);

    let outcome;

    try {
      outcome = await documents.commit(userId, record.id);
    } catch (failure) {
      setError(whyCommitFailed(failure));
      setBusy(false);
      return;
    }

    if (outcome.status !== 'committed') {
      setError(outcome.detail ?? `Nothing was committed (${outcome.status}).`);
      setBusy(false);
      return;
    }

    const written = `${outcome.rows_written} record${outcome.rows_written === 1 ? '' : 's'} from ${file.name}`;

    setRows(null);
    onCommitted?.(written);

    // Past the point of no return: the rows are on disk, so a failure from here says what was
    // written rather than claiming nothing was.
    try {
      setRecord(await documents.read(userId, record.id));
    } catch {
      setError(`${written} were written. This card could not be refreshed to show it.`);
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

      {record?.status === 'extracted' && record.can_remap && !remapping && (
        <button
          type="button"
          onClick={() => setRemapping(true)}
          className="text-[11.5px] text-[#8ba09c] underline decoration-dotted underline-offset-2 transition hover:text-[#18312f]"
        >
          A column was read wrongly? Set them yourself
        </button>
      )}

      {(record?.status === 'needs_mapping' || (remapping && record)) && (
        <Mapping
          userId={userId}
          importId={record!.id}
          onConfirmed={async (updated) => {
            setRecord(updated);
            setRemapping(false);
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

/**
 * Name the failure, because the three that can happen here need three different answers.
 *
 * A 404 means the import is not this user's or is gone, and no amount of retrying helps. A 5xx means
 * the write itself broke and the transaction rolled back, which is worth reporting with the server's
 * own detail. Anything with no status never reached the server at all — a restart mid-request during
 * development is the usual cause — and retrying is exactly right. One sentence covering all three
 * told a reader nothing and sent them to the backend log for something the response already said.
 */
function whyCommitFailed(failure: unknown): string {
  if (failure instanceof ApiError) {
    if (failure.status === 404) {
      return 'That import is not yours, or no longer exists (404). Nothing was written.';
    }

    if (failure.status >= 500) {
      return `The server failed while writing (${failure.status}). Nothing was written — ${failure.message}`;
    }

    return `The commit was refused (${failure.status}) — ${failure.message}`;
  }

  return 'The server could not be reached, so nothing was written. Try again.';
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
