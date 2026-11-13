'use client';

import { useCallback, useState } from 'react';

import { documents } from '@/lib/api';
import type { DocumentStatus, DocumentView } from '@/lib/types';

/**
 * The files sitting in the composer, each uploaded the moment it is picked.
 *
 * Uploading on pick rather than on send overlaps reading the file with typing the message, so the
 * file is usually checked before the message is finished. Each file is its own request, so one
 * bad file never holds back the others.
 *
 * A chip is keyed locally, because it is drawn with its spinner before the server has given the
 * upload an id. Removing a chip only drops it from the message: the upload stays saved, unused.
 */

export interface Attachment {
  /** Stable for the life of the chip, including before an id exists. */
  key: string;
  name: string;
  documentId?: number;
  status: DocumentStatus | 'uploading';
  rowCount: number;
  openQuestions: number;
  /** Pages only the model can read, waiting for the person's OK. */
  modelPages: number;
  /** True when this exact file was uploaded before, so the earlier upload came back. */
  repeat: boolean;
  error?: string;
}

const newKey = () => Math.random().toString(36).slice(2, 10);

function fromDocument(document: DocumentView, previous: Attachment): Attachment {
  return {
    ...previous,
    documentId: document.id,
    status: document.status,
    rowCount: document.rows.length,
    openQuestions: document.checks.open_questions ?? 0,
    modelPages: document.pending_pages?.count ?? 0,
    repeat: document.duplicate,
    error: document.error_message ?? undefined,
  };
}

export function useUploads() {
  const [attachments, setAttachments] = useState<Attachment[]>([]);

  const amend = useCallback((key: string, change: (item: Attachment) => Attachment) => {
    setAttachments((current) => current.map((item) => (item.key === key ? change(item) : item)));
  }, []);

  /** Upload every picked file on its own and draw a chip for each, filled in as each answers. */
  const add = useCallback(
    (picked: File[]) => {
      const started = picked.map((file) => ({
        file,
        chip: { key: newKey(), name: file.name, status: 'uploading' as const, rowCount: 0, openQuestions: 0, modelPages: 0, repeat: false },
      }));

      setAttachments((current) => [...current, ...started.map((item) => item.chip)]);

      for (const { file, chip } of started) {
        documents
          .upload(file)
          .then((document) => amend(chip.key, (current) => fromDocument(document, current)))
          .catch((error: unknown) => {
            const message = error instanceof Error ? error.message : 'That upload failed';

            amend(chip.key, (current) => ({ ...current, status: 'failed', error: message }));
          });
      }
    },
    [amend],
  );

  /** Read a locked PDF with the password typed into its chip. The password is not kept here. */
  const unlock = useCallback(
    (key: string, documentId: number, password: string) => {
      amend(key, (current) => ({ ...current, status: 'uploading', error: undefined }));

      documents
        .unlock(documentId, password)
        .then((document) => amend(key, (current) => fromDocument(document, current)))
        .catch((error: unknown) => {
          const message = error instanceof Error ? error.message : 'That password could not be sent';

          amend(key, (current) => ({ ...current, status: 'needs_password', error: message }));
        });
    },
    [amend],
  );

  /** Drop one chip from the message. The upload itself stays saved. */
  const remove = useCallback((key: string) => {
    setAttachments((current) => current.filter((one) => one.key !== key));
  }, []);

  /** Refresh one chip after its review changed, such as a confirmed mapping or an approval. */
  const refresh = useCallback(
    (document: DocumentView) => {
      setAttachments((current) =>
        current.map((item) => (item.documentId === document.id ? fromDocument(document, item) : item)),
      );
    },
    [],
  );

  /** Empty the composer once its files have gone with a sent message. */
  const clear = useCallback(() => setAttachments([]), []);

  const reading = attachments.some((item) => item.status === 'uploading');

  // Every upload that reached the server goes to the planner, failed ones too, so it can say why.
  const documentIds = attachments
    .map((item) => item.documentId)
    .filter((id): id is number => typeof id === 'number');

  return { attachments, add, remove, unlock, refresh, clear, reading, documentIds };
}
