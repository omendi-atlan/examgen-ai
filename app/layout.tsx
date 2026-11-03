import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "EXAMGEN AI — Examination & Learning Intelligence",
  description: "Generate, practise and review subject-specific examinations."
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
