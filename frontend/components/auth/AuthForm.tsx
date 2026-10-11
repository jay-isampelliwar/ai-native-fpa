'use client';

import { Eye, EyeOff, LoaderCircle } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { ApiError, auth } from '@/lib/api';
import { signedIn, useSession } from '@/lib/session';
import Orb from '@/components/ui/Orb';

const MIN_PASSWORD = 6;

/**
 * The sign-in and sign-up card. One component, because the two differ only by the name field,
 * the button label and where the footer link goes.
 *
 * Someone already signed in who opens this page is sent straight to the chat.
 */
export default function AuthForm({ mode }: { mode: 'signin' | 'signup' }) {
  const router = useRouter();
  const session = useSession();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const signup = mode === 'signup';

  useEffect(() => {
    if (session.status === 'signed-in') router.replace('/');
  }, [session.status, router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();

    if (busy) return;

    if (signup && password.length < MIN_PASSWORD) {
      setError(`Password must be at least ${MIN_PASSWORD} characters.`);
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const user = signup
        ? await auth.signUp(name.trim(), email.trim(), password)
        : await auth.signIn(email.trim(), password);

      signedIn(user);
      router.replace('/');
    } catch (caught) {
      setError(describe(caught));
      setBusy(false);
    }
  }

  return (
    <div className="app-backdrop flex min-h-dvh items-center justify-center px-4 py-8">
      <div className="glass-pane w-full max-w-[400px] p-6 sm:p-8">
        <div className="flex flex-col items-center text-center">
          <Orb size={56} />

          <h1 className="mt-5 text-[22px] font-semibold tracking-[-0.015em] text-primary">
            {signup ? 'Create your account' : 'Welcome back'}
          </h1>

          <p className="mt-1.5 text-[13px] text-secondary">
            {signup ? 'Start planning your money with Mosaic.' : 'Sign in to continue to Mosaic.'}
          </p>
        </div>

        <form onSubmit={submit} className="mt-7 flex flex-col gap-4" noValidate>
          {signup && (
            <Field label="Full name" htmlFor="name">
              <input
                id="name"
                type="text"
                autoComplete="name"
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Rohan Sharma"
                className={INPUT}
              />
            </Field>
          )}

          <Field label="Email" htmlFor="email">
            <input
              id="email"
              type="email"
              autoComplete="email"
              inputMode="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              className={INPUT}
            />
          </Field>

          <Field label="Password" htmlFor="password">
            <span className="relative block">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete={signup ? 'new-password' : 'current-password'}
                required
                minLength={signup ? MIN_PASSWORD : undefined}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={signup ? `At least ${MIN_PASSWORD} characters` : 'Your password'}
                className={`${INPUT} pr-10`}
              />

              <button
                type="button"
                onClick={() => setShowPassword((shown) => !shown)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                className="absolute top-1/2 right-2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md text-muted transition hover:text-primary"
              >
                {showPassword ? <EyeOff size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
              </button>
            </span>
          </Field>

          {error && (
            <p
              role="alert"
              className="rounded-lg px-3 py-2 text-[12.5px] leading-[1.45]"
              style={{ background: 'var(--negative-soft)', color: 'var(--negative)' }}
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy || !email.trim() || !password || (signup && !name.trim())}
            className="mt-1 flex h-11 items-center justify-center gap-2 rounded-xl text-[14px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: 'var(--gradient-send)', color: 'var(--on-accent)' }}
          >
            {busy && <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />}
            {signup ? 'Create account' : 'Sign in'}
          </button>
        </form>

        <p className="mt-6 text-center text-[13px] text-secondary">
          {signup ? 'Already have an account?' : 'New to Mosaic?'}{' '}
          <Link
            href={signup ? '/signin' : '/signup'}
            className="font-semibold text-accent hover:underline"
          >
            {signup ? 'Sign in' : 'Create an account'}
          </Link>
        </p>
      </div>
    </div>
  );
}

const INPUT =
  'w-full rounded-xl border border-line bg-panel px-3.5 py-2.5 text-[14px] text-primary transition placeholder:text-muted focus:border-accent focus:outline-none';

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1.5 block text-[12px] font-medium text-secondary">
        {label}
      </label>
      {children}
    </div>
  );
}

/** Turn a failed call into one line a person can act on. */
function describe(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Could not reach the server. Please try again.';

  if (error.status === 401 || error.status === 409) return error.message;

  if (error.status === 422) return `Please enter a valid email, and a password of at least ${MIN_PASSWORD} characters.`;

  return 'Something went wrong. Please try again.';
}
