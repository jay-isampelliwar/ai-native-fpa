/**
 * The input forms the planner can open beside the chat, fixed in code.
 *
 * The agent only picks a form and prefills values it already knows. Field names match the backend's
 * `FORM_FIELDS` in `app/agent/forms.py`, which drops any name it does not know. Required fields match
 * what the matching save tool needs, so a sent form rarely comes back asking for more.
 */

import type { FormKind, FormValue } from '@/lib/types';

export type FieldType = 'text' | 'money' | 'number' | 'percent' | 'year' | 'date' | 'select' | 'boolean';

export interface FieldSpec {
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
  placeholder?: string;
  hint?: string;
  options?: { value: string; label: string }[];
}

export interface FormSpec {
  kind: FormKind;
  title: string;
  /** One line under the title saying what the form is for. */
  lead: string;
  fields: FieldSpec[];
}

/** `half_yearly` → `Half yearly`, for option labels taken from backend enum values. */
function words(value: string): string {
  const spaced = value.replace(/_/g, ' ');

  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function options(values: string[]): { value: string; label: string }[] {
  return values.map((value) => ({ value, label: words(value) }));
}

const FREQUENCY = options(['monthly', 'quarterly', 'half_yearly', 'yearly']);

export const FORMS: Record<FormKind, FormSpec> = {
  goal: {
    kind: 'goal',
    title: 'Goal',
    lead: 'What are you saving for, and by when?',
    fields: [
      {
        name: 'goal_type',
        label: 'Goal type',
        type: 'select',
        required: true,
        options: options(['house', 'education', 'retirement', 'marriage', 'emergency', 'vehicle', 'travel', 'other']),
      },
      { name: 'name', label: 'Name', type: 'text', required: true, placeholder: 'Construct home' },
      { name: 'target_amount', label: "Amount needed, in today's money", type: 'money', required: true, placeholder: '15,00,000' },
      { name: 'target_year', label: 'Year you need it', type: 'year', required: true, placeholder: '2030' },
      { name: 'priority', label: 'Priority (1 is most important)', type: 'number', placeholder: '1' },
      { name: 'family_member_name', label: 'For a family member', type: 'text', placeholder: 'Leave empty if it is for you' },
    ],
  },
  income: {
    kind: 'income',
    title: 'Income',
    lead: 'Money that comes in regularly, like salary or rent.',
    fields: [
      {
        name: 'source_type',
        label: 'Income type',
        type: 'select',
        required: true,
        options: options(['salary', 'rent', 'business', 'freelance', 'pension', 'other']),
      },
      { name: 'name', label: 'Name', type: 'text', required: true, placeholder: 'Infosys salary' },
      { name: 'amount', label: 'Amount each time', type: 'money', required: true, placeholder: '70,000' },
      { name: 'frequency', label: 'How often', type: 'select', options: FREQUENCY },
      { name: 'yearly_growth_rate', label: 'Yearly raise', type: 'percent', placeholder: '8' },
      { name: 'start_date', label: 'Started on', type: 'date' },
    ],
  },
  expense: {
    kind: 'expense',
    title: 'Expense',
    lead: 'Money that goes out regularly. Loan EMIs and premiums go with the loan or policy.',
    fields: [
      {
        name: 'category',
        label: 'Category',
        type: 'select',
        required: true,
        options: options([
          'rent', 'maintenance', 'groceries', 'electricity', 'water', 'gas', 'mobile_internet', 'fuel',
          'public_transport', 'vehicle_maintenance', 'education', 'child_care', 'elder_care', 'medicines',
          'doctor_visits', 'fitness', 'dining_out', 'food_delivery', 'clothing', 'shopping', 'electronics',
          'entertainment', 'subscriptions', 'travel', 'household_help', 'personal_care', 'pets', 'gifts',
          'donations', 'family_support',
        ]),
      },
      { name: 'name', label: 'Name', type: 'text', required: true, placeholder: 'House rent' },
      { name: 'amount', label: 'Amount each time', type: 'money', required: true, placeholder: '25,000' },
      { name: 'frequency', label: 'How often', type: 'select', options: FREQUENCY },
      { name: 'is_essential', label: 'This is a must-pay', type: 'boolean' },
      { name: 'end_date', label: 'Stops on', type: 'date' },
    ],
  },
  holding: {
    kind: 'holding',
    title: 'Stock or mutual fund',
    lead: 'Type the name as you know it. The planner finds the exact fund or stock.',
    fields: [
      { name: 'instrument_name', label: 'Stock or fund name', type: 'text', required: true, placeholder: 'Parag Parikh Flexi Cap' },
      {
        name: 'plan',
        label: 'Plan (for a fund)',
        type: 'select',
        options: options(['direct_growth', 'direct_idcw', 'regular_growth', 'regular_idcw']),
      },
      { name: 'units', label: 'Units or shares', type: 'number', placeholder: '551.24', hint: 'Give units, amount, or both.' },
      { name: 'amount', label: 'Amount you invested', type: 'money', placeholder: '1,00,000' },
      { name: 'folio_number', label: 'Folio number', type: 'text' },
    ],
  },
  loan: {
    kind: 'loan',
    title: 'Loan',
    lead: 'A loan you are repaying. Its EMI is saved here, not as an expense.',
    fields: [
      {
        name: 'loan_type',
        label: 'Loan type',
        type: 'select',
        required: true,
        options: options(['home', 'car', 'personal', 'education', 'gold', 'other']),
      },
      { name: 'lender', label: 'Lender', type: 'text', required: true, placeholder: 'HDFC Bank' },
      { name: 'principal', label: 'Original loan amount', type: 'money', required: true },
      { name: 'outstanding', label: 'Still to pay', type: 'money', required: true },
      { name: 'interest_rate', label: 'Interest rate', type: 'percent', required: true, placeholder: '8.5' },
      { name: 'emi', label: 'Monthly EMI', type: 'money', required: true },
      { name: 'start_date', label: 'Started on', type: 'date', required: true },
      { name: 'end_date', label: 'Last EMI on', type: 'date', required: true },
    ],
  },
  insurance: {
    kind: 'insurance',
    title: 'Insurance policy',
    lead: 'Life, health or other cover. Its premium is saved here, not as an expense.',
    fields: [
      {
        name: 'policy_type',
        label: 'Policy type',
        type: 'select',
        required: true,
        options: options(['term', 'health', 'life', 'ulip', 'vehicle', 'other']),
      },
      { name: 'insurer', label: 'Insurer', type: 'text', required: true, placeholder: 'LIC' },
      { name: 'cover_amount', label: 'Cover amount', type: 'money', required: true },
      { name: 'premium', label: 'Premium each time', type: 'money', required: true },
      { name: 'premium_frequency', label: 'Premium paid', type: 'select', options: FREQUENCY },
      { name: 'policy_name', label: 'Policy name', type: 'text' },
      { name: 'start_date', label: 'Started on', type: 'date' },
      { name: 'renewal_date', label: 'Renews on', type: 'date' },
    ],
  },
};

/** The value as the input shows it: text for every type but a checkbox. */
export function inputValue(value: FormValue | undefined): string {
  if (value === undefined || typeof value === 'boolean') return '';

  return String(value);
}

/** Turn what was typed into what is sent: numbers for money and counts, true or false for a checkbox. */
export function cleanValue(field: FieldSpec, raw: FormValue | undefined): FormValue | undefined {
  if (raw === undefined || raw === '') return undefined;

  if (field.type === 'boolean') return Boolean(raw);

  if (['money', 'number', 'percent', 'year'].includes(field.type)) {
    const number = Number(String(raw).replace(/[₹,\s]/g, ''));

    return Number.isFinite(number) ? number : String(raw);
  }

  return String(raw).trim() || undefined;
}

/** The first problem with the values, in plain words, or null when the form can be sent. */
export function problemWith(spec: FormSpec, values: Record<string, FormValue>): string | null {
  for (const field of spec.fields) {
    const value = cleanValue(field, values[field.name]);

    if (field.required && value === undefined) return `Please fill in ${field.label.toLowerCase()}.`;

    if (value !== undefined && ['money', 'number', 'percent', 'year'].includes(field.type) && typeof value !== 'number') {
      return `${field.label} must be a number.`;
    }
  }

  if (spec.kind === 'holding' && !inputValue(values.units).trim() && !inputValue(values.amount).trim()) {
    return 'Please give the units or the amount you invested.';
  }

  return null;
}
