import type { Metadata } from "next";
import "./globals.css";
import { MainNav } from "@/components/MainNav";
import { SystemStatusBar } from "@/components/SystemStatusBar";

export const metadata: Metadata = {
  title: "Autonomous QA Platform",
  description: "Register apps, crawl, generate Cucumber tests, and run scenarios",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SystemStatusBar />
        <main className="mx-auto max-w-6xl px-4 py-6">
          <MainNav />
          {children}
        </main>
      </body>
    </html>
  );
}
