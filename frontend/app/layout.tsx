import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import { headers } from 'next/headers';

import { THEME_BOOTSTRAP } from '@/lib/theme';
import './globals.css';

/**
 * Inter, for its tabular figures.
 *
 * Nearly every number on this screen sits in a column or counts up in place, and
 * both need digits of equal width. Inter ships proper tabular numerals, which is
 * the reason it is preferred here over a face chosen for its headlines.
 */
const inter = Inter({ variable: '--font-inter', subsets: ['latin'], display: 'swap' });

const title = 'Mosaic — your AI financial planner';
const description =
  'A conversational financial planner. Ask about your money and watch the picture update.';

export const viewport: Viewport = {
  colorScheme: 'dark light',
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#090c0a' },
    { media: '(prefers-color-scheme: light)', color: '#f5f6f2' },
  ],
};

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const rawHost = requestHeaders.get('host') ?? 'localhost:3000';
  const hostname = rawHost.split(':')[0].toLowerCase();
  const local = hostname === 'localhost' || hostname === '127.0.0.1';
  const origin = new URL(local ? `http://${rawHost}` : `https://${rawHost}`);
  const socialImage = new URL('/og.png', origin).href;

  return {
    metadataBase: origin,
    title,
    description,
    icons: { icon: '/favicon.png' },
    openGraph: {
      title,
      description,
      type: 'website',
      siteName: 'Mosaic',
      images: [{ url: socialImage, width: 1731, height: 909, alt: 'Mosaic financial overview' }],
    },
    twitter: { card: 'summary_large_image', title, description, images: [socialImage] },
  };
}

export default function RootLayout({ children }: LayoutProps<'/'>) {
  // The bootstrap script below rewrites `data-theme` before React hydrates, so this
  // one attribute is expected to differ from the server's markup.
  // `suppressHydrationWarning` is what stops React reporting that as a mismatch for
  // every reader who chose light.
  return (
    <html lang="en" data-theme="dark" className="h-full" suppressHydrationWarning>
      <head>
        {/* Before first paint, so a reader who chose light is never shown a frame
            of dark. React cannot do this from an effect — that runs after paint. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body className={`${inter.variable} h-full antialiased`}>{children}</body>
    </html>
  );
}
