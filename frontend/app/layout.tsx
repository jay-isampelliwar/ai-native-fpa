import type { Metadata } from 'next';
import { Manrope, Newsreader } from 'next/font/google';
import { headers } from 'next/headers';
import './globals.css';

const manrope = Manrope({ variable: '--font-manrope', subsets: ['latin'] });
const newsreader = Newsreader({ variable: '--font-newsreader', subsets: ['latin'] });

const title = 'Farline — See the life your money can support';
const description =
  'A calm financial planner that turns your accounts, goals, and what-ifs into one living path forward.';

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
      siteName: 'Farline',
      images: [{ url: socialImage, width: 1731, height: 909, alt: 'Farline financial life path' }],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [socialImage],
    },
  };
}

export default function RootLayout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" className="h-full">
      <body className={`${manrope.variable} ${newsreader.variable} flex min-h-full flex-col antialiased`}>
        {children}
      </body>
    </html>
  );
}
