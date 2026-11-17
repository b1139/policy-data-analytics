"use client";

import React, { useState } from "react";
import {
  TrendingUp,
  Users,
  Factory,
  Globe2,
  Wallet,
  Hourglass,
  Sparkles,
  ArrowRight,
  ExternalLink,
  ShieldCheck,
  ChevronRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface PolicyIndicatorsHubProps {
  onSelectQuery: (query: string, autoSubmit?: boolean) => void;
}

export function PolicyIndicatorsHub({ onSelectQuery }: PolicyIndicatorsHubProps) {
  const [activeTab, setActiveTab] = useState<
    "gdp" | "industry" | "population" | "aging" | "trade" | "income"
  >("gdp");

  return (
    <div className="space-y-6">
      {/* 1. National Indicators KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <Card className="p-3 bg-white border-slate-200 shadow-sm border-l-4 border-l-emerald-500">
          <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
            Real GDP Growth
          </div>
          <div className="text-xl font-bold text-slate-900 mt-0.5">+3.6%</div>
          <div className="text-[10px] text-emerald-600 font-medium flex items-center gap-1 mt-0.5">
            <TrendingUp className="h-2.5 w-2.5" />
            2024 YoY Rebound
          </div>
        </Card>

        <Card className="p-3 bg-white border-slate-200 shadow-sm border-l-4 border-l-blue-500">
          <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
            Total Population
          </div>
          <div className="text-xl font-bold text-slate-900 mt-0.5">6.04M</div>
          <div className="text-[10px] text-slate-500 font-medium mt-0.5">
            4.18M Resident Pool
          </div>
        </Card>

        <Card className="p-3 bg-white border-slate-200 shadow-sm border-l-4 border-l-rose-500">
          <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
            Fertility Rate (TFR)
          </div>
          <div className="text-xl font-bold text-rose-600 mt-0.5">0.97</div>
          <div className="text-[10px] text-rose-500 font-medium mt-0.5">
            Births / Woman (Low)
          </div>
        </Card>

        <Card className="p-3 bg-white border-slate-200 shadow-sm border-l-4 border-l-purple-500">
          <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
            Elderly Ratio (65+)
          </div>
          <div className="text-xl font-bold text-purple-700 mt-0.5">19.9%</div>
          <div className="text-[10px] text-purple-600 font-medium mt-0.5">
            29.8 Dependency / 100
          </div>
        </Card>

        <Card className="p-3 bg-white border-slate-200 shadow-sm border-l-4 border-l-teal-500">
          <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
            Median HH Income
          </div>
          <div className="text-xl font-bold text-slate-900 mt-0.5">S$10,869</div>
          <div className="text-[10px] text-teal-600 font-medium mt-0.5">
            +2.8% Real Monthly
          </div>
        </Card>

        <Card className="p-3 bg-white border-slate-200 shadow-sm border-l-4 border-l-indigo-500">
          <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
            NODX Exports
          </div>
          <div className="text-xl font-bold text-indigo-700 mt-0.5">+4.2%</div>
          <div className="text-[10px] text-indigo-600 font-medium mt-0.5">
            Electronics Upswing
          </div>
        </Card>
      </div>

      {/* 2. Interactive Policy Intelligence Dashboard Section */}
      <Card className="border-slate-200 shadow-sm bg-white overflow-hidden">
        <CardHeader className="p-4 md:p-6 pb-3 border-b border-slate-100 bg-slate-50/50">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="bg-blue-50 text-sg-blue border-blue-200 text-[10px] uppercase font-bold tracking-wider">
                  Live Policy Intelligence
                </Badge>
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                  SingStat &amp; Ministry Benchmarks
                </span>
              </div>
              <CardTitle className="text-lg font-bold text-slate-900 mt-1">
                Singapore National Policy Indicators &amp; Trends
              </CardTitle>
              <CardDescription className="text-xs text-slate-600">
                Explore official demographic, macroeconomic, industrial, trade, and income metrics.
              </CardDescription>
            </div>

            {/* Navigation Tabs */}
            <div className="flex flex-wrap gap-1 p-1 bg-slate-200/60 rounded-lg text-xs font-medium">
              <button
                type="button"
                onClick={() => setActiveTab("gdp")}
                className={cn(
                  "px-2.5 py-1 rounded-md transition-all flex items-center gap-1.5",
                  activeTab === "gdp"
                    ? "bg-white text-sg-blue shadow-sm font-semibold"
                    : "text-slate-600 hover:text-slate-900"
                )}
              >
                <TrendingUp className="h-3.5 w-3.5" />
                6-Yr GDP
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("industry")}
                className={cn(
                  "px-2.5 py-1 rounded-md transition-all flex items-center gap-1.5",
                  activeTab === "industry"
                    ? "bg-white text-sg-blue shadow-sm font-semibold"
                    : "text-slate-600 hover:text-slate-900"
                )}
              >
                <Factory className="h-3.5 w-3.5" />
                Industries
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("population")}
                className={cn(
                  "px-2.5 py-1 rounded-md transition-all flex items-center gap-1.5",
                  activeTab === "population"
                    ? "bg-white text-sg-blue shadow-sm font-semibold"
                    : "text-slate-600 hover:text-slate-900"
                )}
              >
                <Users className="h-3.5 w-3.5" />
                Population &amp; Fertility
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("aging")}
                className={cn(
                  "px-2.5 py-1 rounded-md transition-all flex items-center gap-1.5",
                  activeTab === "aging"
                    ? "bg-white text-sg-blue shadow-sm font-semibold"
                    : "text-slate-600 hover:text-slate-900"
                )}
              >
                <Hourglass className="h-3.5 w-3.5" />
                Aged vs Youth
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("trade")}
                className={cn(
                  "px-2.5 py-1 rounded-md transition-all flex items-center gap-1.5",
                  activeTab === "trade"
                    ? "bg-white text-sg-blue shadow-sm font-semibold"
                    : "text-slate-600 hover:text-slate-900"
                )}
              >
                <Globe2 className="h-3.5 w-3.5" />
                Trade &amp; FDI
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("income")}
                className={cn(
                  "px-2.5 py-1 rounded-md transition-all flex items-center gap-1.5",
                  activeTab === "income"
                    ? "bg-white text-sg-blue shadow-sm font-semibold"
                    : "text-slate-600 hover:text-slate-900"
                )}
              >
                <Wallet className="h-3.5 w-3.5" />
                Household Income
              </button>
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-4 md:p-6 space-y-4">
          {/* TAB 1: 6-YEAR GDP GROWTH */}
          {activeTab === "gdp" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
              <div className="lg:col-span-7 space-y-3">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="font-semibold text-slate-800">
                    Singapore Annual Real GDP Growth Rate (%) (2018–2024)
                  </span>
                  <span className="text-[11px] text-muted-foreground">Source: SingStat Table M015661</span>
                </div>

                {/* Visual Chart: 6-Year GDP Trend */}
                <div className="h-48 w-full bg-slate-50 rounded-lg p-3 border border-slate-100 flex flex-col justify-between">
                  <div className="flex-1 flex items-end justify-between gap-3 px-2 pt-4 pb-2 border-b border-slate-200">
                    {[
                      { year: "2018", gdp: 3.5, height: 50, color: "bg-blue-500" },
                      { year: "2019", gdp: 1.3, height: 25, color: "bg-blue-400" },
                      { year: "2020", gdp: -3.9, height: 35, color: "bg-rose-400", isNeg: true },
                      { year: "2021", gdp: 8.9, height: 95, color: "bg-emerald-500" },
                      { year: "2022", gdp: 3.8, height: 52, color: "bg-blue-500" },
                      { year: "2023", gdp: 1.1, height: 22, color: "bg-blue-400" },
                      { year: "2024", gdp: 3.6, height: 51, color: "bg-emerald-600" },
                    ].map((item) => (
                      <div key={item.year} className="flex-1 flex flex-col items-center gap-1 group relative">
                        <span className="text-[10px] font-bold text-slate-700 font-mono">
                          {item.gdp > 0 ? `+${item.gdp}%` : `${item.gdp}%`}
                        </span>
                        <div className="w-full max-w-[36px] bg-slate-200/50 rounded-t h-28 flex items-end justify-center">
                          <div
                            style={{ height: `${item.height}%` }}
                            className={cn(
                              "w-full rounded-t transition-all duration-300 group-hover:opacity-85",
                              item.color
                            )}
                          />
                        </div>
                        <span className="text-[11px] font-medium text-slate-500">{item.year}</span>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 px-1">
                    <span>* 2020 reflects COVID contraction (-3.9%), followed by 2021 rebound (+8.9%) and 2024 normalization (+3.6%)</span>
                  </div>
                </div>
              </div>

              <div className="lg:col-span-5 space-y-4 bg-slate-50/70 p-4 rounded-xl border border-slate-200/80">
                <div className="space-y-1.5">
                  <h4 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <TrendingUp className="h-4 w-4 text-emerald-600" />
                    Macroeconomic Analysis Highlights
                  </h4>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    Singapore achieved a 3.6% GDP expansion in 2024, rebounding from 1.1% in 2023. Growth was driven by the recovery in global semiconductor cycle and sustained expansion in wholesale trade and finance.
                  </p>
                </div>

                <div className="space-y-2 pt-1 text-xs">
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">6-Year Compound Growth</span>
                    <span className="font-semibold text-slate-800 font-mono">+2.6% p.a.</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">Key Growth Engine</span>
                    <span className="font-semibold text-slate-800">Electronics &amp; FinTech</span>
                  </div>
                </div>

                <Button
                  onClick={() =>
                    onSelectQuery(
                      "Evaluate Singapore's real GDP growth trajectory, annual growth rates, and economic cycles over the last 6 years (2018-2024)"
                    )
                  }
                  className="w-full bg-sg-blue hover:bg-[#0A3D6B] text-white gap-2 text-xs h-9 shadow-sm"
                >
                  <Sparkles className="h-3.5 w-3.5 text-sg-amber" />
                  Run Autonomous In-Depth Analysis on 6-Yr GDP
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}

          {/* TAB 2: INDUSTRY GDP */}
          {activeTab === "industry" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
              <div className="lg:col-span-7 space-y-3">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="font-semibold text-slate-800">
                    Singapore GDP Share by Key Industry Cluster (%)
                  </span>
                  <span className="text-[11px] text-muted-foreground">Source: SingStat Table M015671</span>
                </div>

                {/* Horizontal Bar Breakdown */}
                <div className="space-y-2.5 p-3 bg-slate-50 rounded-lg border border-slate-100">
                  {[
                    { name: "Manufacturing (Electronics, Biomedical, Precision)", share: 21.6, color: "bg-blue-600" },
                    { name: "Wholesale & Retail Trade", share: 18.4, color: "bg-sky-500" },
                    { name: "Financial & Insurance Services", share: 14.2, color: "bg-indigo-600" },
                    { name: "Transportation & Storage (Aviation, Maritime)", share: 7.1, color: "bg-teal-500" },
                    { name: "Information & Communications (ICT / AI)", share: 5.8, color: "bg-purple-600" },
                    { name: "Professional & Business Services", share: 6.2, color: "bg-amber-500" },
                  ].map((ind) => (
                    <div key={ind.name} className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="font-medium text-slate-700">{ind.name}</span>
                        <span className="font-bold text-slate-900 font-mono">{ind.share}%</span>
                      </div>
                      <div className="w-full h-2.5 bg-slate-200/70 rounded-full overflow-hidden">
                        <div
                          style={{ width: `${ind.share * 3.5}%` }}
                          className={cn("h-full rounded-full", ind.color)}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="lg:col-span-5 space-y-4 bg-slate-50/70 p-4 rounded-xl border border-slate-200/80">
                <div className="space-y-1.5">
                  <h4 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <Factory className="h-4 w-4 text-blue-600" />
                    Sectoral Performance Dynamics
                  </h4>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    Manufacturing accounts for over one-fifth of Singapore&apos;s economy, anchored by semiconductors and advanced biopharma. ICT is the fastest growing sector with over 7.5% annual expansion since 2020.
                  </p>
                </div>

                <div className="space-y-2 pt-1 text-xs">
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">Fastest Growing Sector</span>
                    <span className="font-semibold text-purple-700">Information &amp; Comms (+7.6%)</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">Largest Contributor</span>
                    <span className="font-semibold text-slate-800">Manufacturing (21.6%)</span>
                  </div>
                </div>

                <Button
                  onClick={() =>
                    onSelectQuery(
                      "Compare GDP growth rates and sectoral economic contribution across major Singapore industries: Manufacturing, Finance, ICT, and Wholesale Trade"
                    )
                  }
                  className="w-full bg-sg-blue hover:bg-[#0A3D6B] text-white gap-2 text-xs h-9 shadow-sm"
                >
                  <Sparkles className="h-3.5 w-3.5 text-sg-amber" />
                  Analyze Sectoral GDP &amp; Industry Trends
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}

          {/* TAB 3: POPULATION & FERTILITY */}
          {activeTab === "population" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
              <div className="lg:col-span-7 space-y-3">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="font-semibold text-slate-800">
                    Singapore Total Fertility Rate (TFR) &amp; Population Growth
                  </span>
                  <span className="text-[11px] text-muted-foreground">Source: SingStat Table M810011</span>
                </div>

                <div className="p-4 bg-slate-50 rounded-lg border border-slate-100 space-y-4">
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div className="p-3 bg-white rounded-md border border-slate-200">
                      <div className="text-[11px] text-slate-500">Total Population</div>
                      <div className="text-lg font-bold text-slate-900 mt-1">6.04M</div>
                      <div className="text-[10px] text-emerald-600">+2.0% YoY</div>
                    </div>
                    <div className="p-3 bg-white rounded-md border border-slate-200">
                      <div className="text-[11px] text-slate-500">Resident Fertility</div>
                      <div className="text-lg font-bold text-rose-600 mt-1">0.97</div>
                      <div className="text-[10px] text-rose-500">Replacement: 2.1</div>
                    </div>
                    <div className="p-3 bg-white rounded-md border border-slate-200">
                      <div className="text-[11px] text-slate-500">Life Expectancy</div>
                      <div className="text-lg font-bold text-blue-700 mt-1">83.0 yrs</div>
                      <div className="text-[10px] text-slate-500">Top tier globally</div>
                    </div>
                  </div>

                  <div className="space-y-1.5 pt-2">
                    <div className="flex justify-between text-xs text-slate-600">
                      <span>Total Fertility Rate Trend (2018: 1.14 → 2024: 0.97)</span>
                      <span className="font-semibold text-rose-600">-14.9% decline</span>
                    </div>
                    <div className="w-full h-2.5 bg-slate-200 rounded-full overflow-hidden flex">
                      <div className="h-full bg-rose-500 w-[46%]" title="2024: 0.97 (46% of replacement 2.1)" />
                      <div className="h-full bg-slate-300 w-[54%]" title="Gap to 2.1 replacement level" />
                    </div>
                  </div>
                </div>
              </div>

              <div className="lg:col-span-5 space-y-4 bg-slate-50/70 p-4 rounded-xl border border-slate-200/80">
                <div className="space-y-1.5">
                  <h4 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <Users className="h-4 w-4 text-blue-600" />
                    Demographic Transition Context
                  </h4>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    Singapore&apos;s Total Fertility Rate dipped below 1.0 for the first time in 2023–2024 to 0.97. High life expectancy (83.0 years) coupled with fewer resident births accelerates the transition toward a super-aged society.
                  </p>
                </div>

                <div className="space-y-2 pt-1 text-xs">
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">Annual Marriages</span>
                    <span className="font-semibold text-slate-800">~28,300 unions</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">Citizen Population</span>
                    <span className="font-semibold text-slate-800">3.64 Million (60.3%)</span>
                  </div>
                </div>

                <Button
                  onClick={() =>
                    onSelectQuery(
                      "Analyze Singapore population growth trends, total fertility rate (TFR), marriage rates, and life expectancy from 2018 to 2024"
                    )
                  }
                  className="w-full bg-sg-blue hover:bg-[#0A3D6B] text-white gap-2 text-xs h-9 shadow-sm"
                >
                  <Sparkles className="h-3.5 w-3.5 text-sg-amber" />
                  Analyze Population, Marriage &amp; Fertility
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}

          {/* TAB 4: AGED VS YOUTH */}
          {activeTab === "aging" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
              <div className="lg:col-span-7 space-y-3">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="font-semibold text-slate-800">
                    Demographic Shift: Elderly (65+) vs Youth (0–14) Proportions
                  </span>
                  <span className="text-[11px] text-muted-foreground">Source: SingStat Population Benchmark</span>
                </div>

                <div className="p-4 bg-slate-50 rounded-lg border border-slate-100 space-y-4">
                  <div className="space-y-3">
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="font-semibold text-purple-700">Elderly Population (Aged 65+)</span>
                        <span className="font-bold text-purple-800 font-mono">19.9% in 2024 (Up from 14.4% in 2018)</span>
                      </div>
                      <div className="w-full h-3 bg-slate-200 rounded-full overflow-hidden">
                        <div className="h-full bg-purple-600 rounded-full w-[65%]" />
                      </div>
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="font-semibold text-amber-600">Youth Population (Aged 0–14)</span>
                        <span className="font-bold text-amber-700 font-mono">13.5% in 2024 (Down from 15.3% in 2018)</span>
                      </div>
                      <div className="w-full h-3 bg-slate-200 rounded-full overflow-hidden">
                        <div className="h-full bg-amber-500 rounded-full w-[45%]" />
                      </div>
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="font-semibold text-slate-700">Old-Age Dependency Ratio</span>
                        <span className="font-bold text-slate-900 font-mono">29.8 per 100 working-age (20–64)</span>
                      </div>
                      <div className="w-full h-3 bg-slate-200 rounded-full overflow-hidden">
                        <div className="h-full bg-slate-700 rounded-full w-[52%]" />
                      </div>
                    </div>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    By 2030, approximately 1 in 4 Singaporeans (24.1%) will be aged 65 and above, necessitating increased healthcare funding and eldercare infrastructure.
                  </p>
                </div>
              </div>

              <div className="lg:col-span-5 space-y-4 bg-slate-50/70 p-4 rounded-xl border border-slate-200/80">
                <div className="space-y-1.5">
                  <h4 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <Hourglass className="h-4 w-4 text-purple-700" />
                    Silver Demographics &amp; Labor Policy
                  </h4>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    Seniors now significantly outnumber children in Singapore. Policy initiatives focus on the Silver Support Scheme, CPF retirement adequacy enhancements, and senior worker re-employment grants up to age 70.
                  </p>
                </div>

                <div className="space-y-2 pt-1 text-xs">
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">Current Senior Cohort</span>
                    <span className="font-semibold text-purple-700">~830,000 citizens/PRs</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">Working-Age to Senior Ratio</span>
                    <span className="font-semibold text-slate-800">3.4 : 1 (Projected 2.3 : 1 by 2030)</span>
                  </div>
                </div>

                <Button
                  onClick={() =>
                    onSelectQuery(
                      "Assess aging population trends versus youth demographic growth in Singapore: elderly (65+) dependency ratio compared with youth cohort (2018-2024)"
                    )
                  }
                  className="w-full bg-sg-blue hover:bg-[#0A3D6B] text-white gap-2 text-xs h-9 shadow-sm"
                >
                  <Sparkles className="h-3.5 w-3.5 text-sg-amber" />
                  Analyze Aged vs Youth Dependency Dynamics
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}

          {/* TAB 5: TRADE & INVESTMENTS */}
          {activeTab === "trade" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
              <div className="lg:col-span-7 space-y-3">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="font-semibold text-slate-800">
                    Singapore External Trade, NODX &amp; Inward FDI
                  </span>
                  <span className="text-[11px] text-muted-foreground">Source: Enterprise Singapore &amp; EDB</span>
                </div>

                <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-lg border border-slate-100">
                  <div className="p-3 bg-white rounded border border-slate-200 space-y-1">
                    <div className="text-[11px] text-slate-500">Total Merchandise Trade</div>
                    <div className="text-lg font-bold text-slate-900 font-mono">S$1.28 Trillion</div>
                    <div className="text-[10px] text-emerald-600">+6.6% YoY Expansion</div>
                  </div>

                  <div className="p-3 bg-white rounded border border-slate-200 space-y-1">
                    <div className="text-[11px] text-slate-500">NODX Exports</div>
                    <div className="text-lg font-bold text-indigo-700 font-mono">+4.2% YoY</div>
                    <div className="text-[10px] text-indigo-600">Rebound from -13.1% in 2023</div>
                  </div>

                  <div className="p-3 bg-white rounded border border-slate-200 space-y-1">
                    <div className="text-[11px] text-slate-500">Annual FDI Commitments</div>
                    <div className="text-lg font-bold text-blue-700 font-mono">S$12.7 Billion</div>
                    <div className="text-[10px] text-slate-600">EDB Target Surpassed</div>
                  </div>

                  <div className="p-3 bg-white rounded border border-slate-200 space-y-1">
                    <div className="text-[11px] text-slate-500">Top Export Market</div>
                    <div className="text-lg font-bold text-slate-900">China, US, EU</div>
                    <div className="text-[10px] text-slate-500">Diverse Global Trade Ties</div>
                  </div>
                </div>
              </div>

              <div className="lg:col-span-5 space-y-4 bg-slate-50/70 p-4 rounded-xl border border-slate-200/80">
                <div className="space-y-1.5">
                  <h4 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <Globe2 className="h-4 w-4 text-indigo-600" />
                    External Trade &amp; Investment Health
                  </h4>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    Singapore remains one of the world&apos;s most trade-intensive economies (trade-to-GDP ratio ~300%). Sustained foreign direct investment in semiconductor foundries and AI data centres anchors high-value employment.
                  </p>
                </div>

                <div className="space-y-2 pt-1 text-xs">
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">Trade-to-GDP Ratio</span>
                    <span className="font-semibold text-slate-800">~310%</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">FDI Anchor Sectors</span>
                    <span className="font-semibold text-slate-800">Advanced Mfg &amp; FinTech</span>
                  </div>
                </div>

                <Button
                  onClick={() =>
                    onSelectQuery(
                      "Examine Singapore external trade performance, Non-Oil Domestic Exports (NODX) growth, and foreign direct investment (FDI) inflows (2020-2024)"
                    )
                  }
                  className="w-full bg-sg-blue hover:bg-[#0A3D6B] text-white gap-2 text-xs h-9 shadow-sm"
                >
                  <Sparkles className="h-3.5 w-3.5 text-sg-amber" />
                  Analyze Trade, Exports &amp; Investment Trends
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}

          {/* TAB 6: HOUSEHOLD INCOME & GINI */}
          {activeTab === "income" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
              <div className="lg:col-span-7 space-y-3">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="font-semibold text-slate-800">
                    Median Monthly Household Income from Work (Including CPF)
                  </span>
                  <span className="text-[11px] text-muted-foreground">Source: SingStat Key Household Trends</span>
                </div>

                <div className="p-4 bg-slate-50 rounded-lg border border-slate-100 space-y-3">
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div className="p-2.5 bg-white rounded border border-slate-200">
                      <div className="text-[10px] text-slate-500">2021 Median</div>
                      <div className="text-base font-bold text-slate-800 font-mono">S$9,520</div>
                    </div>
                    <div className="p-2.5 bg-white rounded border border-slate-200">
                      <div className="text-[10px] text-slate-500">2022 Median</div>
                      <div className="text-base font-bold text-slate-800 font-mono">S$10,099</div>
                    </div>
                    <div className="p-2.5 bg-white rounded border border-slate-200 bg-teal-50/50 border-teal-200">
                      <div className="text-[10px] text-teal-700 font-semibold">2023 Median</div>
                      <div className="text-base font-bold text-teal-800 font-mono">S$10,869</div>
                    </div>
                  </div>

                  <div className="space-y-1.5 pt-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-slate-600">Gini Coefficient (After taxes &amp; transfers)</span>
                      <span className="font-bold text-teal-700 font-mono">0.371 (Historical Low)</span>
                    </div>
                    <div className="w-full h-2 bg-slate-200 rounded-full overflow-hidden">
                      <div className="h-full bg-teal-600 w-[37.1%]" />
                    </div>
                    <div className="text-[10px] text-slate-500 flex justify-between">
                      <span>Before transfers: 0.433</span>
                      <span>Government redistribution effect: -0.062</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="lg:col-span-5 space-y-4 bg-slate-50/70 p-4 rounded-xl border border-slate-200/80">
                <div className="space-y-1.5">
                  <h4 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <Wallet className="h-4 w-4 text-teal-700" />
                    Income Growth &amp; Redistribution
                  </h4>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    Median household income rose to S$10,869, representing a 2.8% real increase after accounting for inflation. Progressive Wage Model expansions and targeted Assurance Package payouts moderated inequality.
                  </p>
                </div>

                <div className="space-y-2 pt-1 text-xs">
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">Per Member Median</span>
                    <span className="font-semibold text-slate-800 font-mono">S$3,500 / month</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                    <span className="text-slate-500">Assurance Package Impact</span>
                    <span className="font-semibold text-emerald-700">Offset bottom 20% inflation</span>
                  </div>
                </div>

                <Button
                  onClick={() =>
                    onSelectQuery(
                      "Analyze median monthly household income from work, wage percentiles, and Gini coefficient in Singapore over the last 3 years"
                    )
                  }
                  className="w-full bg-sg-blue hover:bg-[#0A3D6B] text-white gap-2 text-xs h-9 shadow-sm"
                >
                  <Sparkles className="h-3.5 w-3.5 text-sg-amber" />
                  Analyze Household Income &amp; Wage Distribution
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
