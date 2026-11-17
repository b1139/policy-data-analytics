"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  History,
  LayoutDashboard,
  Cpu,
  Menu,
  X,
  Database,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAnalyses } from "@/hooks/useAnalysis";

const navigationItems = [
  {
    name: "Dashboard",
    href: "/dashboard",
    icon: LayoutDashboard,
  },
  {
    name: "Analysis History",
    href: "/dashboard/history",
    icon: History,
  },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { data: analysesData } = useAnalyses({ limit: 1 });
  const totalCount = analysesData?.total;

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-slate-50/50">
      {/* Mobile Top Header */}
      <header className="md:hidden flex items-center justify-between px-4 py-3 bg-white border-b sticky top-0 z-40">
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-sg-blue flex items-center justify-center text-white font-bold text-sm shadow-sm">
            SG
          </div>
          <div>
            <span className="font-semibold text-sm tracking-tight text-slate-900 block leading-tight">
              Policy Analytics
            </span>
            <span className="text-[11px] text-muted-foreground block">
              Multi-Agent Intelligence
            </span>
          </div>
        </div>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-2 rounded-md hover:bg-slate-100 text-slate-600 focus:outline-none"
          aria-label="Toggle Navigation"
        >
          {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </header>

      {/* Sidebar for Desktop & Mobile Overlay */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 bg-white border-r flex flex-col transition-transform duration-200 ease-in-out md:static md:translate-x-0",
          mobileMenuOpen ? "translate-x-0" : "-translate-x-0 hidden md:flex"
        )}
      >
        {/* Sidebar Brand Header */}
        <div className="h-16 px-6 border-b flex items-center justify-between">
          <Link
            href="/dashboard"
            onClick={() => setMobileMenuOpen(false)}
            className="flex items-center gap-3 group"
          >
            <div className="h-9 w-9 rounded-lg bg-sg-blue flex items-center justify-center text-white font-bold text-base shadow-sm group-hover:bg-[#0A3D6B] transition-colors">
              SG
            </div>
            <div>
              <div className="font-bold text-sm text-slate-900 tracking-tight flex items-center gap-1.5">
                Policy Analytics
                <span className="inline-block w-2 h-2 rounded-full bg-sg-amber animate-pulse" />
              </div>
              <div className="text-[11px] font-medium text-slate-500">
                Agentic Gov Platform
              </div>
            </div>
          </Link>
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="md:hidden p-1.5 text-slate-400 hover:text-slate-600 rounded"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          <div className="px-3 pb-2 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Platform Menu
          </div>
          {navigationItems.map((item) => {
            const isActive =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            const Icon = item.icon;

            return (
              <Link
                key={item.name}
                href={item.href}
                onClick={() => setMobileMenuOpen(false)}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-sg-blue/10 text-sg-blue font-semibold border border-sg-blue/20"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100/80"
                )}
              >
                <Icon
                  className={cn(
                    "h-4 w-4 shrink-0",
                    isActive ? "text-sg-blue" : "text-slate-400"
                  )}
                />
                <span className="flex-1">{item.name}</span>
                {item.href === "/dashboard/history" && typeof totalCount === "number" && (
                  <span
                    className={cn(
                      "px-2 py-0.5 text-[11px] font-semibold font-mono rounded-full",
                      isActive
                        ? "bg-sg-blue/20 text-sg-blue"
                        : "bg-slate-100 text-slate-600 group-hover:bg-slate-200"
                    )}
                  >
                    {totalCount}
                  </span>
                )}
              </Link>
            );
          })}

          <div className="pt-6 px-3 pb-2 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Connected Agents
          </div>
          <div className="space-y-1 px-1">
            <div className="flex items-center justify-between px-2.5 py-1.5 text-xs text-slate-600 rounded">
              <span className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-blue-500" />
                Coordinator
              </span>
              <span className="text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded font-mono">
                ReAct
              </span>
            </div>
            <div className="flex items-center justify-between px-2.5 py-1.5 text-xs text-slate-600 rounded">
              <span className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                Extraction
              </span>
              <span className="text-[10px] bg-emerald-50 text-emerald-700 px-1.5 py-0.5 rounded font-mono">
                SingStat MCP
              </span>
            </div>
            <div className="flex items-center justify-between px-2.5 py-1.5 text-xs text-slate-600 rounded">
              <span className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-purple-500" />
                Analytics
              </span>
              <span className="text-[10px] bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded font-mono">
                Plotly
              </span>
            </div>
          </div>
        </nav>

        {/* Sidebar Footer System Info */}
        <div className="p-4 border-t bg-slate-50/50 space-y-2">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <ShieldCheck className="h-4 w-4 text-emerald-600 shrink-0" />
            <span>GovTech Compliant Env</span>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-slate-400">
            <Database className="h-3.5 w-3.5 text-slate-400 shrink-0" />
            <span>SingStat & Data.gov.sg v2</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
