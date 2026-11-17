"use client";

import React from "react";
import Link from "next/link";
import { History, PlusCircle, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HistoryList } from "@/components/history/HistoryList";

export default function HistoryPage() {
  return (
    <div className="container mx-auto p-4 md:p-8 max-w-6xl space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b">
        <div>
          <div className="flex items-center gap-2">
            <History className="h-6 w-6 text-sg-blue" />
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Analysis History
            </h1>
          </div>
          <p className="text-sm text-slate-600 mt-1">
            Browse and review past multi-agent policy research runs, insights, charts, and exports.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Link href="/dashboard">
            <Button className="bg-sg-blue hover:bg-[#0A3D6B] text-white gap-2 text-sm shadow-xs">
              <PlusCircle className="h-4 w-4" />
              <span>New Analysis</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* History List Component */}
      <HistoryList />
    </div>
  );
}
