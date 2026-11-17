import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "SG Policy Analytics | Agentic Policy Data Analytics Platform",
  description:
    "Autonomous multi-agent system for public policy data analysis, extraction, and synthesis",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="font-sans antialiased min-h-screen bg-slate-50/50 text-foreground selection:bg-sg-blue/10 selection:text-sg-blue">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
