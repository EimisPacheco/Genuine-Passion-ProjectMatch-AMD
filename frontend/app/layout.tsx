import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Multi-Agent Passion Intelligence · Gemma on the AMD MI300X",
  description: "A swarm of Gemma 4 31B agents on the AMD MI300X discovers what people can't stop building — in seconds.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="mx-auto max-w-6xl px-6 py-6">
          <header className="mb-8 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3">
              <div className="h-7 w-1.5 rounded bg-brand" />
              <div>
                <div className="text-lg font-semibold text-slate-100">
                  Multi-Agent Passion Intelligence
                </div>
                <div className="text-xs text-slate-500">
                  Gemma 4 31B agents on the AMD MI300X — discover what people can’t stop building.
                </div>
              </div>
            </Link>
            {/* No speed race: Track 3 doesn't score speed or tokens, so the GPU is
                spent on more thinking rather than on a faster number. */}
            <nav className="flex items-center gap-4 text-sm">
              <Link href="/" className="text-slate-400 hover:text-brand">
                Investigate
              </Link>
              <Link href="/pool" className="text-slate-400 hover:text-brand">
                🗂 Talent pool
              </Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
