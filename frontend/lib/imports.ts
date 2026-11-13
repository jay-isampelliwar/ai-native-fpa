/**
 * Small helpers the import review shares: names for tables and fields, how a row is titled, and
 * how a raw value reads. Field kinds come from the backend once and are kept for the session.
 */

import { documents } from '@/lib/api';
import type { ImportFields, ImportRowView } from '@/lib/types';

export const TABLE_LABELS: Record<string, string> = {
  users: 'Your profile',
  family_members: 'Family',
  income_sources: 'Income',
  expenses: 'Expenses',
  transactions: 'Transactions',
  holdings: 'Stocks and funds',
  sip_plans: 'SIPs',
  bank_accounts: 'Bank accounts',
  fixed_deposits: 'Fixed deposits',
  retirement_accounts: 'Retirement accounts',
  physical_assets: 'Property and gold',
  loans: 'Loans',
  credit_cards: 'Credit cards',
  insurance_policies: 'Insurance',
  goals: 'Goals',
};

/** Fields the code fills itself, never shown for editing. */
export const HIDDEN_FIELDS = new Set(['holding_row_number', 'instrument', 'asset_type']);

const MONEY_KINDS = new Set(['money']);

let fieldsRequest: Promise<ImportFields> | null = null;

/** The field kinds and choice values, fetched once and shared by every panel. */
export function loadFields(): Promise<ImportFields> {
  fieldsRequest ??= documents.fields().catch((error: unknown) => {
    fieldsRequest = null;
    throw error;
  });

  return fieldsRequest;
}

/** `current_value` → `Current value`. */
export function humanize(name: string): string {
  const spaced = name.replace(/_/g, ' ');

  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function tableLabel(table: string): string {
  return TABLE_LABELS[table] ?? humanize(table);
}

/** The values a row would save: its parsed values with the user's edits on top. */
export function effectiveData(row: ImportRowView): Record<string, unknown> {
  return { ...row.parsed_data, ...(row.edited_data ?? {}) };
}

/** A short name for a row, such as the fund or the expense it holds. */
export function rowTitle(row: ImportRowView): string {
  const data = effectiveData(row);
  const instrument = row.resolved.instrument?.name;

  if (instrument) return instrument;

  for (const key of ['security_name', 'name', 'description', 'bank_name', 'lender', 'insurer', 'loan_type', 'account_type', 'policy_type']) {
    const value = data[key];

    if (typeof value === 'string' && value) return value;
  }

  return tableLabel(row.target_table);
}

/** One value as a person reads it: rupees for money, Yes or No for flags, a dash for nothing. */
export function showValue(value: unknown, kind?: string): string {
  if (value === null || value === undefined || value === '') return '—';

  if (typeof value === 'boolean') return value ? 'Yes' : 'No';

  if (kind && MONEY_KINDS.has(kind)) {
    const amount = Number(value);

    if (Number.isFinite(amount)) return `₹${amount.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
  }

  if (typeof value === 'string' && /^[a-z]+(_[a-z]+)*$/.test(value)) return humanize(value);

  return String(value);
}

/** The field an error is about, from text like "units: missing". */
export function errorField(error: string): string {
  return error.split(':')[0].trim();
}
