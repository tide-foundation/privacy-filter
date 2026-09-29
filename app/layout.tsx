import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Tide · Cleanse me!', description: 'Cleanse your documents.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
