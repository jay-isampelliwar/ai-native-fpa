'use client';

import { AlertTriangle, FileText, Loader2, Lock, X } from 'lucide-react';
import { useState } from 'react';

import type { Attachment } from '@/lib/useUploads';

/**
 * The attached files, drawn above the composer while they are read.
 *
 * A chip says what is happening to one file in words rather than only through a spinner, because
 * the states differ in what they ask of the reader: a file being read needs patience, a locked one
 * needs a password, a refused one needs a different file. Drawing all three as "loading" would
 * hide the two that a person can actually act on.
 *
 * The password field appears inside the chip rather than as a dialog. It belongs to one file, and a
 * modal over the conversation would make it look like the app is asking about the whole message.
 *
 * Nothing here is a form. The password is sent on Enter or on the button, and a wrong one leaves
 * the chip exactly where it was with the reason under it, so the next attempt costs one field.
 */

function describe(item: Attachment): { label: string; tone: string } {
  switch (item.status) {
    case 'uploading':
      return { label: 'Uploading…', tone: 'text-muted' };
    case 'uploaded':
    case 'extracting':
      return { label: 'Reading…', tone: 'text-muted' };
    case 'extracted':
      return {
        label: item.repeat
          ? 'Already imported'
          : `${item.rowCount} row${item.rowCount === 1 ? '' : 's'} found`,
        tone: 'text-secondary',
      };
    case 'locked':
      return { label: 'Needs a password', tone: 'text-warning' };
    case 'needs_mapping':
      return { label: 'Layout not recognised', tone: 'text-warning' };
    case 'committed':
      return { label: 'Saved', tone: 'text-positive' };
    case 'rejected':
      return { label: 'Refused', tone: 'text-muted' };
    default:
      return { label: 'Could not be read', tone: 'text-negative' };
  }
}

export default function FileChips({
  attachments,
  onRemove,
  onUnlock,
}: {
  attachments: Attachment[];
  onRemove: (key: string) => void;
  onUnlock: (key: string, password: string) => void;
}) {
  if (attachments.length === 0) return null;

  return (
    <ul className="mb-2 flex flex-col gap-1.5">
      {attachments.map((item) => (
        <Chip key={item.key} item={item} onRemove={onRemove} onUnlock={onUnlock} />
      ))}
    </ul>
  );
}

function Chip({
  item,
  onRemove,
  onUnlock,
}: {
  item: Attachment;
  onRemove: (key: string) => void;
  onUnlock: (key: string, password: string) => void;
}) {
  const [password, setPassword] = useState('');

  const { label, tone } = describe(item);
  const working = item.status === 'uploading' || item.status === 'uploaded' || item.status === 'extracting';

  return (
    <li className="rounded-xl border border-line bg-panel-subtle px-2.5 py-2">
      <div className="flex items-center gap-2">
        <span className="flex-none text-muted" aria-hidden="true">
          {working ? (
            <Loader2 size={14} className="animate-spin" />
          ) : item.status === 'locked' ? (
            <Lock size={14} />
          ) : item.status === 'failed' ? (
            <AlertTriangle size={14} />
          ) : (
            <FileText size={14} />
          )}
        </span>

        <span className="min-w-0 flex-1 truncate text-[12.5px] text-primary" title={item.name}>
          {item.name}
        </span>

        <span className={`flex-none text-[11.5px] ${tone}`}>{label}</span>

        <button
          type="button"
          onClick={() => onRemove(item.key)}
          aria-label={`Remove ${item.name}`}
          className="grid h-6 w-6 flex-none place-items-center rounded-lg text-muted transition hover:text-primary"
        >
          <X size={13} aria-hidden="true" />
        </button>
      </div>

      {item.status === 'locked' && (
        <div className="mt-2 flex items-center gap-1.5 pl-6">
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== 'Enter' || !password) return;

              event.preventDefault();
              onUnlock(item.key, password);
              setPassword('');
            }}
            placeholder="PDF password"
            aria-label={`Password for ${item.name}`}
            className="min-w-0 flex-1 rounded-lg border border-line bg-panel px-2 py-1 text-[12px] text-primary outline-none placeholder:text-muted"
          />

          <button
            type="button"
            disabled={!password}
            onClick={() => {
              onUnlock(item.key, password);
              setPassword('');
            }}
            className="flex-none rounded-lg px-2.5 py-1 text-[12px] font-medium transition disabled:cursor-not-allowed disabled:opacity-40"
            style={{ background: 'var(--accent)', color: 'var(--on-accent)' }}
          >
            Open
          </button>
        </div>
      )}

      {item.error && item.status !== 'extracted' && (
        <p className="mt-1.5 pl-6 text-[11.5px] leading-[1.45] text-secondary">{item.error}</p>
      )}
    </li>
  );
}
