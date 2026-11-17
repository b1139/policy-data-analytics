import React from "react";
import { DatabaseZap } from "lucide-react";

interface NoDataProps {
  message?: string;
  className?: string;
}

/** Consistent empty state shown when there is no data for the user's query. */
export function NoData({ message, className = "" }: NoDataProps) {
  return (
    <div
      role="status"
      className={`flex flex-col items-center justify-center text-center gap-2 py-8 ${className}`}
    >
      <DatabaseZap className="h-6 w-6 text-slate-400" />
      <span className="text-sm font-semibold text-slate-600">No Data</span>
      {message && <span className="text-xs text-muted-foreground max-w-sm">{message}</span>}
    </div>
  );
}
