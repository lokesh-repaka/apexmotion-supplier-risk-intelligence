import React, { useState } from 'react';
import {
  Shield,
  ArrowRight,
  ExternalLink,
  Cpu,
  CheckCircle2,
  Lock,
  Activity,
} from 'lucide-react';

interface LandingPageProps {
  onLaunchWorkbench: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onLaunchWorkbench }) => {
  const [isDiagramModalOpen, setIsDiagramModalOpen] = useState(false);

  return (
    <div className="bg-[#060911] text-slate-100 antialiased selection:bg-sky-600 selection:text-white min-h-screen">
      
      {/* ================= TOP NAVIGATION BAR ================= */}
      <nav className="sticky top-0 z-50 backdrop-blur-xl bg-[#080d1a]/90 border-b border-slate-800/80 px-6 py-3.5 transition-all">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          
          {/* Brand & Status */}
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-sky-500 via-indigo-600 to-cyan-400 flex items-center justify-center text-white shadow-lg shadow-sky-500/30">
              <Shield className="w-6 h-6 stroke-[2.3]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-extrabold tracking-tight text-white">ApexMotion <span className="text-sky-400">Risk Intelligence</span></span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  AWS US-East-1 Production Live
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-medium">Multi-Agent Supply Chain Risk &amp; Governance Platform</p>
            </div>
          </div>

          {/* Navigation Links */}
          <div className="hidden md:flex items-center gap-6 text-xs font-semibold text-slate-300">
            <a href="#about" className="hover:text-sky-400 transition-colors">Overview</a>
            <a href="#nanocore" className="hover:text-sky-400 transition-colors">The NanoCore Incident</a>
            <a href="#triad" className="hover:text-sky-400 transition-colors">The Triad Principle</a>
            <a href="#architecture" className="hover:text-sky-400 transition-colors">Architecture Blueprint</a>
            <a href="#agents" className="hover:text-sky-400 transition-colors">Multi-Agent Swarm</a>
            <a href="#hitl" className="hover:text-sky-400 transition-colors">HITL Governance</a>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <a
              href="https://github.com/lokesh-repaka/apexmotion-supplier-risk-intelligence"
              target="_blank"
              rel="noopener noreferrer"
              className="px-3.5 py-2 rounded-xl text-xs font-semibold text-slate-300 hover:text-white bg-slate-900 hover:bg-slate-800 border border-slate-700/80 transition-all flex items-center gap-1.5"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>GitHub</span>
            </a>
            <button
              type="button"
              onClick={onLaunchWorkbench}
              className="group px-4 py-2 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-sky-600 via-indigo-600 to-sky-500 hover:from-sky-500 hover:to-indigo-500 shadow-lg shadow-sky-500/25 border border-sky-400/30 transition-all flex items-center gap-2 transform active:scale-95 cursor-pointer"
            >
              <span>🚀 Launch Application Workbench</span>
              <ArrowRight className="w-3.5 h-3.5 transform group-hover:translate-x-1 transition-transform" />
            </button>
          </div>

        </div>
      </nav>

      {/* ================= HERO SECTION ================= */}
      <header id="about" className="relative pt-16 pb-20 overflow-hidden border-b border-slate-800/80 bg-gradient-to-b from-[#0a1224] via-[#080d1a] to-[#060911]">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[350px] bg-sky-600/10 rounded-full blur-3xl pointer-events-none"></div>
        <div className="absolute top-1/3 left-1/4 w-[400px] h-[250px] bg-indigo-600/10 rounded-full blur-3xl pointer-events-none"></div>

        <div className="max-w-7xl mx-auto px-6 relative z-10">
          
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs font-semibold mb-6">
            <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping"></span>
            <span>Production Release 1.0.0 • 1,202 Offline Tests (100% Passed) • Forward Deployed Engineering Deliverable</span>
          </div>

          <h1 className="text-4xl lg:text-6xl font-extrabold tracking-tight text-white max-w-4xl leading-[1.15]">
            Autonomous Supplier Risk Intelligence for <span className="bg-gradient-to-r from-sky-400 via-indigo-300 to-cyan-400 bg-clip-text text-transparent">Global Manufacturing</span>
          </h1>

          <p className="mt-6 text-base lg:text-lg text-slate-300 max-w-3xl leading-relaxed">
            Engineered for <strong className="text-white">ApexMotion</strong> (Tier-1 EV parts, battery, and electronics manufacturer with 4,500 suppliers across 38 countries and 65,000 SKUs). It replaces blind manual supplier monitoring with a <strong className="text-sky-400">multi-agent LangGraph swarm</strong>, multi-tier Neptune graph traversal, deterministic Python risk math, and cryptographically signed human spend approval gates.
          </p>

          {/* Key Metrics Strip */}
          <div className="mt-10 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl">
            <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-sm">
              <div className="text-2xl font-black text-sky-400">1,202 / 1,202</div>
              <div className="text-xs text-slate-400 mt-1 font-medium">Tests Passed (1,086 Pytest + 116 Vitest)</div>
            </div>
            <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-sm">
              <div className="text-2xl font-black text-emerald-400">$18M / Year</div>
              <div className="text-xs text-slate-400 mt-1 font-medium">Supplier Disruption Loss Target Mitigated</div>
            </div>
            <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-sm">
              <div className="text-2xl font-black text-amber-400">100% Deterministic</div>
              <div className="text-xs text-slate-400 mt-1 font-medium">Days of Cover &amp; Exposure (Zero LLM Math)</div>
            </div>
            <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-sm">
              <div className="text-2xl font-black text-cyan-400">ECDSA P-256</div>
              <div className="text-xs text-slate-400 mt-1 font-medium">AWS KMS Dual-Approval HITL Spend Gating</div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={onLaunchWorkbench}
              className="px-6 py-3.5 rounded-xl text-sm font-bold text-white bg-gradient-to-r from-sky-600 via-indigo-600 to-sky-500 hover:from-sky-500 hover:to-indigo-500 shadow-xl shadow-sky-500/25 transition-all flex items-center gap-2 transform active:scale-95 cursor-pointer"
            >
              <span>🚀 Launch Operational Workbench</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            <a
              href="#architecture"
              className="px-6 py-3.5 rounded-xl text-sm font-semibold text-slate-200 bg-slate-900 hover:bg-slate-800 border border-slate-700 transition-all flex items-center gap-2"
            >
              <span>🏛️ Inspect Architecture Blueprint</span>
            </a>
            <a
              href="https://github.com/lokesh-repaka/apexmotion-supplier-risk-intelligence"
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3.5 rounded-xl text-sm font-semibold text-slate-300 hover:text-white bg-transparent hover:bg-slate-800/40 border border-slate-700/60 transition-all flex items-center gap-2"
            >
              <ExternalLink className="w-4 h-4" />
              <span>GitHub Repository</span>
            </a>
          </div>

        </div>
      </header>

      {/* ================= THE NANOCORE INCIDENT ================= */}
      <section id="nanocore" className="py-20 border-b border-slate-800/80 bg-[#060911]">
        <div className="max-w-7xl mx-auto px-6">
          
          <div className="max-w-3xl mb-12">
            <span className="text-xs font-bold tracking-widest text-amber-400 uppercase">Canonical Ground-Truth Benchmark</span>
            <h2 className="text-3xl font-extrabold text-white mt-2">The NanoCore Semiconductor Disruption</h2>
            <p className="text-sm text-slate-400 mt-3 leading-relaxed">
              ApexMotion’s canonical benchmark incident: A fire at NanoCore Microelectronics (Tier-1 MCU supplier) halts delivery of microcontrollers for ApexMotion Battery Management Systems.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="p-6 rounded-2xl bg-[#0a1224] border border-slate-800">
              <div className="text-xs font-mono uppercase text-sky-400 font-bold">Current Stock</div>
              <div className="text-2xl font-black text-white mt-2">142,000 Units</div>
              <p className="text-xs text-slate-400 mt-2">Daily consumption rate: 18,500 units/day across 3 EV assembly lines.</p>
            </div>

            <div className="p-6 rounded-2xl bg-[#0a1224] border border-slate-800">
              <div className="text-xs font-mono uppercase text-amber-400 font-bold">Days of Cover</div>
              <div className="text-2xl font-black text-amber-400 mt-2">7.68 Days</div>
              <p className="text-xs text-slate-400 mt-2 font-mono">142,000 / 18,500 = 7.6756 days (deterministic float precision).</p>
            </div>

            <div className="p-6 rounded-2xl bg-[#0a1224] border border-slate-800">
              <div className="text-xs font-mono uppercase text-red-400 font-bold">Production Gap</div>
              <div className="text-2xl font-black text-red-400 mt-2">1.32 Days</div>
              <p className="text-xs text-slate-400 mt-2">9-day supplier shipment delay leaves a 24,420 unit deficit.</p>
            </div>

            <div className="p-6 rounded-2xl bg-[#0a1224] border border-slate-800">
              <div className="text-xs font-mono uppercase text-emerald-400 font-bold">Financial Exposure</div>
              <div className="text-2xl font-black text-emerald-400 mt-2">$2,448,105.00</div>
              <p className="text-xs text-slate-400 mt-2 font-mono">24,420 units × $100.25 BOM plant cost per unit.</p>
            </div>
          </div>

        </div>
      </section>

      {/* ================= THE TRIAD OF RESPONSIBILITY ================= */}
      <section id="triad" className="py-20 border-b border-slate-800/80 bg-[#080d1a]">
        <div className="max-w-7xl mx-auto px-6">
          
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="text-xs font-bold tracking-widest text-sky-400 uppercase">Architectural Invariant</span>
            <h2 className="text-3xl font-extrabold text-white mt-2">The Triad of Responsibility</h2>
            <p className="text-sm text-slate-400 mt-3">Non-negotiable architectural separation: AI reasons over evidence, Python computes all numbers, Humans authorize all dollars.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            
            {/* Pillar 1: AI */}
            <div className="p-8 rounded-3xl bg-slate-900/60 border border-sky-500/30">
              <div className="w-12 h-12 rounded-2xl bg-sky-500/20 text-sky-400 flex items-center justify-center mb-6">
                <Cpu className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-white mb-2">1. AI / LLM Domain</h3>
              <p className="text-xs text-sky-400 font-semibold mb-4">Evidence Synthesis &amp; Parsing</p>
              <ul className="space-y-3 text-xs text-slate-300">
                <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" /> Gathers unstructured signals from maritime AIS, news &amp; SEC filings.</li>
                <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" /> Extracts force majeure, penalty clauses &amp; lead times from supplier contracts.</li>
                <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" /> Synthesizes risk dossiers with zero arithmetic permissions.</li>
                <li className="flex items-start gap-2 text-red-400 font-semibold"><span className="text-red-400 font-bold">✕</span> ZERO math calculations or financial decisions permitted.</li>
              </ul>
            </div>

            {/* Pillar 2: Deterministic */}
            <div className="p-8 rounded-3xl bg-slate-900/60 border border-emerald-500/30">
              <div className="w-12 h-12 rounded-2xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center mb-6">
                <Activity className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-white mb-2">2. Deterministic Domain</h3>
              <p className="text-xs text-emerald-400 font-semibold mb-4">100% Python Arithmetic</p>
              <ul className="space-y-3 text-xs text-slate-300">
                <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" /> Computes exact Days of Cover (current stock / daily rate).</li>
                <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" /> Computes Shortage Volume down to individual SKU units.</li>
                <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" /> Calculates Financial Exposure ($2,448,105.00 for NanoCore).</li>
                <li className="flex items-start gap-2 text-emerald-400 font-semibold"><CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" /> Guaranteed zero-hallucination arithmetic compliance.</li>
              </ul>
            </div>

            {/* Pillar 3: Human Authority */}
            <div className="p-8 rounded-3xl bg-slate-900/60 border border-amber-500/30">
              <div className="w-12 h-12 rounded-2xl bg-amber-500/20 text-amber-400 flex items-center justify-center mb-6">
                <Lock className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-white mb-2">3. Human Authority</h3>
              <p className="text-xs text-amber-400 font-semibold mb-4">Cryptographic HITL Spend Gate</p>
              <ul className="space-y-3 text-xs text-slate-300">
                <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" /> Category Manager approval required for spend &le; $100k.</li>
                <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" /> VP Supply Chain dual-signature required for spend &gt; $100k.</li>
                <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" /> AWS KMS ECDSA P-256 cryptographic token minting &amp; replay protection.</li>
                <li className="flex items-start gap-2 text-amber-400 font-semibold"><CheckCircle2 className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" /> Zero autonomous purchase orders or PO releases.</li>
              </ul>
            </div>

          </div>

        </div>
      </section>

      {/* ================= ARCHITECTURE BLUEPRINT ================= */}
      <section id="architecture" className="py-20 border-b border-slate-800/80 bg-[#060911]">
        <div className="max-w-7xl mx-auto px-6">
          
          <div className="flex flex-col md:flex-row md:items-end justify-between mb-12">
            <div>
              <span className="text-xs font-bold tracking-widest text-sky-400 uppercase">System Topology</span>
              <h2 className="text-3xl lg:text-4xl font-extrabold text-white mt-2">C4 Level-2 Component Blueprint</h2>
              <p className="text-sm text-slate-400 mt-2 max-w-2xl">
                End-to-end integration: React 18 SPA, Kafka event streaming, Quarantined Reader prompt firewall, LangGraph multi-agent swarm, Amazon Neptune knowledge graph, and S3 WORM archive.
              </p>
            </div>
            <div className="mt-4 md:mt-0 flex items-center gap-3">
              <button
                type="button"
                onClick={() => setIsDiagramModalOpen(true)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-200 bg-slate-900 hover:bg-slate-800 border border-slate-700 transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <span>🔍 Click to Zoom Architecture</span>
              </button>
            </div>
          </div>

          {/* Architecture Image Card */}
          <div
            onClick={() => setIsDiagramModalOpen(true)}
            className="rounded-3xl border border-slate-800 bg-[#0a1224] p-4 lg:p-6 shadow-2xl relative overflow-hidden group cursor-pointer"
          >
            <div className="relative rounded-2xl overflow-hidden border border-slate-800/80 bg-[#060911]">
              <img
                src="/architecture-diagram.jpg"
                alt="ApexMotion End-to-End System Architecture Blueprint"
                className="w-full h-auto object-contain transition-transform duration-500 group-hover:scale-[1.01]"
              />
            </div>
            <div className="mt-4 flex items-center justify-between text-xs text-slate-400 px-2">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-sky-400"></span>
                <span className="font-mono text-sky-400">Figure 1.0: ApexMotion Supplier Risk Intelligence &amp; Governance Topology</span>
              </div>
              <span>Click to view full-screen diagram</span>
            </div>
          </div>

        </div>
      </section>

      {/* ================= THE 5 SPECIALIST AGENTS ================= */}
      <section id="agents" className="py-20 border-b border-slate-800/80 bg-[#080d1a]">
        <div className="max-w-7xl mx-auto px-6">
          
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="text-xs font-bold tracking-widest text-sky-400 uppercase">LangGraph Multi-Agent Swarm</span>
            <h2 className="text-3xl font-extrabold text-white mt-2">5 Autonomous Risk Specialists</h2>
            <p className="text-sm text-slate-400 mt-3">Single-responsibility agents collaborating over stateful graph checkpoints to investigate supplier disruption signals.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800">
              <div className="text-sm font-bold text-white mb-2 flex items-center gap-2">
                <span className="text-sky-400">01.</span> Triage Agent
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-3">
                Normalizes inbound Kafka events, strips untrusted formatting, scans source credibility, and categorizes disruption type (Financial, Geopolitical, Operational, Logistics).
              </p>
              <div className="text-[11px] font-mono text-slate-500 border-t border-slate-800 pt-2">
                Input: Kafka Event &bull; Output: NormalizedSignal
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800">
              <div className="text-sm font-bold text-white mb-2 flex items-center gap-2">
                <span className="text-sky-400">02.</span> Research Agent
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-3">
                Enriches event context with external web news, corporate filings, customs databases, and AIS maritime vessel transponder coordinates.
              </p>
              <div className="text-[11px] font-mono text-slate-500 border-t border-slate-800 pt-2">
                Tool: WebSearch &bull; Output: EnrichedContext
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800">
              <div className="text-sm font-bold text-white mb-2 flex items-center gap-2">
                <span className="text-sky-400">03.</span> Contract Agent
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-3">
                Executes vector retrieval over OpenSearch contract chunks, parsing force majeure clauses, SLA delay penalties, and contractual alternate supplier terms.
              </p>
              <div className="text-[11px] font-mono text-slate-500 border-t border-slate-800 pt-2">
                Tool: OpenSearch k-NN &bull; Output: LegalClauses
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800">
              <div className="text-sm font-bold text-white mb-2 flex items-center gap-2">
                <span className="text-sky-400">04.</span> Risk Analysis Agent
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-3">
                Traverses the Amazon Neptune multi-tier supply chain graph to map N-tier blast radius, identifies single-source bottleneck parts, and invokes Python math engine.
              </p>
              <div className="text-[11px] font-mono text-slate-500 border-t border-slate-800 pt-2">
                Tool: Neptune Cypher &bull; Output: GraphBlastRadius
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 md:col-span-2">
              <div className="text-sm font-bold text-white mb-2 flex items-center gap-2">
                <span className="text-sky-400">05.</span> Recommendation Agent
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-3">
                Formulates mitigation scenarios: spot-buy buffer stock, transfer inventory between manufacturing plants, or activate qualified alternate suppliers (e.g. Renesas Electronics).
              </p>
              <div className="text-[11px] font-mono text-slate-500 border-t border-slate-800 pt-2">
                Output: RecommendationPlan[] (Pending HITL Dual-Authorization)
              </div>
            </div>

          </div>

        </div>
      </section>

      {/* ================= FINAL LAUNCH CTA ================= */}
      <section className="py-20 bg-[#060911] text-center relative overflow-hidden">
        <div className="max-w-4xl mx-auto px-6 relative z-10">
          
          <div className="w-16 h-16 rounded-2xl bg-sky-500 text-white flex items-center justify-center font-black mx-auto mb-6 shadow-xl shadow-sky-500/30">
            <Shield className="w-8 h-8" />
          </div>

          <h2 className="text-3xl lg:text-5xl font-black text-white tracking-tight">
            Explore the Live Operational Workbench
          </h2>
          
          <p className="mt-4 text-base text-slate-300 max-w-xl mx-auto">
            Interact with live risk alerts, traverse the 400k-node Neptune supplier graph, simulate the NanoCore incident, and test cryptographic HITL spend authorization.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              type="button"
              onClick={onLaunchWorkbench}
              className="w-full sm:w-auto px-8 py-4 rounded-xl text-sm font-bold text-white bg-gradient-to-r from-sky-600 via-indigo-600 to-sky-500 hover:from-sky-500 hover:to-indigo-500 shadow-xl shadow-sky-500/30 transition-all transform active:scale-95 flex items-center justify-center gap-2 cursor-pointer"
            >
              <span>🚀 Launch Operational Risk Workbench</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            <a
              href="https://github.com/lokesh-repaka/apexmotion-supplier-risk-intelligence"
              target="_blank"
              rel="noopener noreferrer"
              className="w-full sm:w-auto px-8 py-4 rounded-xl text-sm font-semibold text-slate-200 bg-slate-900 hover:bg-slate-800 border border-slate-700 transition-all flex items-center justify-center gap-2"
            >
              <ExternalLink className="w-4 h-4" />
              <span>GitHub Repository</span>
            </a>
          </div>

        </div>
      </section>

      {/* ================= FOOTER ================= */}
      <footer className="py-8 bg-[#04060c] border-t border-slate-900 text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-300">ApexMotion Supplier Risk Intelligence Platform</span>
            <span>&bull;</span>
            <span>EURON Consulting FDE Deliverable</span>
          </div>
          <div className="flex items-center gap-6">
            <button type="button" onClick={onLaunchWorkbench} className="hover:text-sky-400 transition cursor-pointer">Workbench</button>
            <a href="https://github.com/lokesh-repaka/apexmotion-supplier-risk-intelligence" target="_blank" rel="noopener noreferrer" className="hover:text-sky-400 transition">GitHub</a>
          </div>
        </div>
      </footer>

      {/* ================= ARCHITECTURE DIAGRAM MODAL ================= */}
      {isDiagramModalOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-4 lg:p-8"
          onClick={() => setIsDiagramModalOpen(false)}
        >
          <div
            className="relative max-w-6xl w-full bg-[#080d1a] border border-slate-800 rounded-3xl p-6 shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Shield className="w-4 h-4 text-sky-400" />
                <span>ApexMotion System Architecture Blueprint (Full Resolution)</span>
              </h3>
              <button
                type="button"
                onClick={() => setIsDiagramModalOpen(false)}
                className="w-8 h-8 rounded-full bg-slate-800 text-slate-400 hover:text-white flex items-center justify-center text-sm font-bold transition cursor-pointer"
              >
                ✕
              </button>
            </div>
            <div className="overflow-auto max-h-[80vh] rounded-xl border border-slate-800 bg-[#060911]">
              <img
                src="/architecture-diagram.jpg"
                alt="Full System Architecture Diagram"
                className="w-full h-auto"
              />
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
