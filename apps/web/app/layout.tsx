import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata, Viewport } from "next";
import { AppShell } from "@/components/layout/app-shell";
import { themeInitScript } from "@/components/layout/theme-toggle";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "ForgeFlow AI", template: "%s · ForgeFlow AI" },
  description: "Autonomous multi-agent software delivery: plan, implement, test, review and verify changes.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0b0d10" },
    { media: "(prefers-color-scheme: light)", color: "#f6f7f8" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${GeistSans.variable} ${GeistMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="font-sans text-sm">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
