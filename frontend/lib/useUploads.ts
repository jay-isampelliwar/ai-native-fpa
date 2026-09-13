'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { documents } from '@/lib/api';
import type { DocumentImport, ImportStatus } from '@/lib/types';

/**
 * The attachments sitting in the composer, uploaded the moment they are picked.
 *
 * Uploading on pick rather than on send is the whole latency strategy. Reading a statement takes
 * seconds and a person takes seconds to type; overlapping the two means the file is usually ready
 * before the message is finished, and the reply is not held behind a parser.
 *
 * A chip is keyed locally rather than by import id, because it exists before the server has
 * answered and has to be drawn — with its spinner — during the upload itself.
 *
 * Polling stops the moment every chip reaches a state that is waiting on a person rather than on
 * the server. `locked` and `needs_mapping` are settled in that sense: nothing more will happen
 * until an answer is given, so continuing to poll would be asking the same question forever.
 *
 * Removing a chip rejects the import rather than only forgetting it here. The bytes are already on
 * the server by then, and a file dropped from the composer should not outlive the intent to send it.
 */

/** States where the server is still working and the client should keep asking. */
const WORKING: ReadonlySet<ImportStatus> = new Set(['uploaded', 'extracting']);

const POLL_INTERVAL_MS = 1000;

export interface Attachment {
  /** Stable for the life of the chip, including before an id exists. */
  key: string;
  name: string;
  importId?: string;
  status: ImportStatus | 'uploading';
  rowCount: number;
  duplicateRows: number;
  /** True when this exact file was already imported, so nothing was read again. */
  repeat: boolean;
  error?: string;
}

const newKey = () => Math.random().toString(36).slice(2, 10);

function fromImport(record: DocumentImport, previous: Attachment): Attachment {
  return {
    ...previous,
    importId: record.id,
    status: record.status,
    rowCount: record.row_count,
    duplicateRows: record.duplicate_rows,
    error: record.error ?? undefined,
  };
}

export function useUploads(userId: number | null) {
  const [attachments, setAttachments] = useState<Attachment[]>([]);

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const amend = useCallback((key: string, change: (item: Attachment) => Attachment) => {
    setAttachments((current) => current.map((item) => (item.key === key ? change(item) : item)));
  }, []);

  /** Upload every picked file at once and draw a chip for each, filled in as the server answers. */
  const add = useCallback(
    async (picked: File[]) => {
      if (typeof userId !== 'number' || picked.length === 0) return;

      const started: Attachment[] = picked.map((file) => ({
        key: newKey(),
        name: file.name,
        status: 'uploading',
        rowCount: 0,
        duplicateRows: 0,
        repeat: false,
      }));

      setAttachments((current) => [...current, ...started]);

      try {
        const response = await documents.upload(userId, picked);

        setAttachments((current) =>
          current.map((item) => {
            const index = started.findIndex((one) => one.key === item.key);
            const answered = index >= 0 ? response.documents[index] : undefined;

            if (!answered) return item;

            return {
              ...item,
              importId: answered.id,
              status: answered.status,
              repeat: answered.duplicate,
            };
          }),
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : 'that upload failed';

        setAttachments((current) =>
          current.map((item) =>
            started.some((one) => one.key === item.key)
              ? { ...item, status: 'failed', error: message }
              : item,
          ),
        );
      }
    },
    [userId],
  );

  /** Drop one attachment, refusing it on the server so its bytes do not linger. */
  const remove = useCallback(
    (key: string) => {
      const item = attachments.find((one) => one.key === key);

      setAttachments((current) => current.filter((one) => one.key !== key));

      if (typeof userId !== 'number' || !item?.importId || item.repeat) return;

      void documents.reject(userId, item.importId).catch(() => {
        // The chip is already gone from the composer; a failed cleanup is not worth reporting.
      });
    },
    [attachments, userId],
  );

  /** Send a password for a locked PDF and let polling pick the file up again. */
  const unlock = useCallback(
    async (key: string, password: string) => {
      const item = attachments.find((one) => one.key === key);

      if (typeof userId !== 'number' || !item?.importId) return;

      amend(key, (current) => ({ ...current, status: 'uploaded', error: undefined }));

      try {
        const record = await documents.unlock(userId, item.importId, password);

        amend(key, (current) => fromImport(record, current));
      } catch (error) {
        const message = error instanceof Error ? error.message : 'that password could not be sent';

        amend(key, (current) => ({ ...current, status: 'locked', error: message }));
      }
    },
    [amend, attachments, userId],
  );

  /** Empty the composer once its attachments have been handed to a sent message. */
  const clear = useCallback(() => setAttachments([]), []);

  // Ask the server about anything it is still working on, and stop as soon as nothing is.
  useEffect(() => {
    if (typeof userId !== 'number') return;

    const working = attachments.filter(
      (item) => item.importId && item.status !== 'uploading' && WORKING.has(item.status),
    );

    if (working.length === 0) return;

    timer.current = setTimeout(() => {
      void Promise.all(
        working.map(async (item) => {
          try {
            const record = await documents.read(userId, item.importId as string);

            amend(item.key, (current) => fromImport(record, current));
          } catch {
            // A single missed poll is not a failure; the next tick asks again.
          }
        }),
      );
    }, POLL_INTERVAL_MS);

    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [amend, attachments, userId]);

  const reading = attachments.some(
    (item) => item.status === 'uploading' || WORKING.has(item.status as ImportStatus),
  );

  // Everything that reached the server goes to the planner, not only what parsed. A locked or
  // unreadable file is something it should mention, and its summary tool answers with the status.
  const importIds = attachments
    .filter((item) => item.importId && item.status !== 'rejected')
    .map((item) => item.importId as string);

  return { attachments, add, remove, unlock, clear, reading, importIds };
}
