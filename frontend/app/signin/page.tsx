import type { Metadata } from 'next';

import AuthForm from '@/components/auth/AuthForm';

export const metadata: Metadata = { title: 'Sign in — Mosaic' };

export default function SignInPage() {
  return <AuthForm mode="signin" />;
}
