import React, { useState } from 'react';
import {
  LayoutDashboard,
  Network,
  Search,
  ShieldCheck,
  FileText,
  Home,
  Menu,
  X,
  Shield,
  Activity,
  CheckCircle2,
  Lock,
} from 'lucide-react';
import { HITLApprovalModal } from './components/HITLApprovalModal/HITLApprovalModal';
import { ApprovalQueueTable } from './components/HITLApprovalModal/ApprovalQueueTable';
import { InvestigationPage } from './pages/InvestigationPage';
import { RiskDashboardPage } from './pages/RiskDashboardPage';
import { SupplierGraphPage } from './pages/SupplierGraphPage';
import { AuditTrailPage } from './pages/AuditTrailPage';
import { LandingPage } from './components/LandingPage/LandingPage';

export type AppView = 'landing' | 'dashboard' | 'graph' | 'investigation' | 'approvals' | 'audit';

interface NavItem {
  id: AppView;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  desc: string;
  badge?: string;
}

const NAV_ITEMS: NavItem[] = [
  {
    id: 'landing',
    label: 'Overview & Blueprint',
    icon: Home,
    desc: 'Architecture, Benchmark & Triad Specs',
  },
  {
    id: 'dashboard',
    label: 'Operational Risk Dashboard',
    icon: LayoutDashboard,
    desc: 'Real-time KPIs, Heatmap & Kafka Stream',
    badge: 'LIVE',
  },
  {
    id: 'graph',
    label: 'Multi-Tier Knowledge Graph',
    icon: Network,
    desc: 'Amazon Neptune 400k Node Topology',
  },
  {
    id: 'investigation',
    label: 'Investigation Case Dossier',
    icon: Search,
    desc: '5-Agent LangGraph Swarm Root Cause',
  },
  {
    id: 'approvals',
    label: 'HITL Spend Approvals',
    icon: ShieldCheck,
    desc: 'KMS ECDSA P-256 Gated Authorization',
    badge: 'GATED',
  },
  {
    id: 'audit',
    label: 'WORM Audit Ledger',
    icon: FileText,
    desc: 'Cryptographic Immutable Compliance Trail',
  },
];

export const App: React.FC = () => {
  const [activeView, setActiveView] = useState<AppView>('landing');
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // If in Landing Page, render clean landing page without top bar, with slide-out sidebar drawer
  if (activeView === 'landing') {
    return (
      <div className="min-h-screen bg-[#060911] text-slate-100 flex flex-col font-sans relative">
        <LandingPage
          onLaunchWorkbench={() => setActiveView('dashboard')}
          onOpenSidebar={() => setIsSidebarOpen(true)}
        />

        {/* Floating Workbench Sidebar Pill on Landing Page */}
        <button
          type="button"
          onClick={() => setIsSidebarOpen(true)}
          className="fixed bottom-6 left-6 z-40 px-4 py-2.5 rounded-full bg-slate-900/95 hover:bg-slate-800 text-slate-200 border border-slate-700/80 shadow-2xl backdrop-blur-md flex items-center gap-2.5 text-xs font-semibold hover:border-sky-500/50 transition-all hover:scale-105 group"
          title="Open Workbench Navigation Sidebar"
        >
          <Menu className="w-4 h-4 text-sky-400 group-hover:rotate-90 transition-transform" />
          <span>Workbench Navigation</span>
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        </button>

        {/* Slide-out Sidebar Drawer for Landing Page */}
        {isSidebarOpen && (
          <div className="fixed inset-0 z-50 flex">
            {/* Backdrop */}
            <div
              className="fixed inset-0 bg-black/75 backdrop-blur-sm transition-opacity"
              onClick={() => setIsSidebarOpen(false)}
            />

            {/* Drawer Panel */}
            <div className="relative w-80 max-w-[85vw] bg-[#080d1a] border-r border-slate-800 flex flex-col justify-between h-full z-10 shadow-2xl animate-in slide-in-from-left duration-200">
              <div className="p-5 flex flex-col gap-4 overflow-y-auto">
                {/* Drawer Header */}
                <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center text-white shadow-md">
                      <Shield className="w-4 h-4 stroke-[2.3]" />
                    </div>
                    <div>
                      <span className="text-sm font-bold text-white">Workbench Navigation</span>
                      <p className="text-[10px] text-slate-400">Direct Module Access</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsSidebarOpen(false)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* Navigation Items */}
                <div className="flex flex-col gap-1.5">
                  {NAV_ITEMS.map(item => {
                    const Icon = item.icon;
                    const isActive = activeView === item.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          setActiveView(item.id);
                          setIsSidebarOpen(false);
                        }}
                        className={`w-full text-left px-3.5 py-3 rounded-xl text-xs font-semibold transition-all flex items-start gap-3 ${
                          isActive
                            ? 'bg-sky-600 text-white shadow-lg shadow-sky-600/20 font-bold'
                            : 'text-slate-300 hover:text-white hover:bg-slate-900 border border-transparent hover:border-slate-800'
                        }`}
                      >
                        <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${isActive ? 'text-white' : 'text-sky-400'}`} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span className="truncate">{item.label}</span>
                            {item.badge && (
                              <span className={`text-[9px] px-1.5 py-0.2 rounded font-mono uppercase ${
                                isActive ? 'bg-white/20 text-white' : 'bg-slate-800 text-sky-400 border border-slate-700'
                              }`}>
                                {item.badge}
                              </span>
                            )}
                          </div>
                          <p className={`text-[10px] truncate mt-0.5 ${isActive ? 'text-sky-100' : 'text-slate-400'}`}>
                            {item.desc}
                          </p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Invariant Footer */}
              <div className="p-4 border-t border-slate-800/80 bg-[#060a14]">
                <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-[10px] font-mono space-y-1.5">
                  <div className="text-emerald-400 font-semibold flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Zero-Hallucination Triad Active</span>
                  </div>
                  <p className="text-slate-400 text-[9px]">100% Python Math • AWS KMS ECDSA P-256 Gating</p>
                </div>
              </div>
            </div>
          </div>
        )}

        <HITLApprovalModal />
      </div>
    );
  }

  // Inside the Application Workbench: Dedicated Left Sidebar layout
  return (
    <div className="min-h-screen bg-[#060911] text-slate-100 flex font-sans">
      {/* Permanent Left Sidebar in Workbench */}
      <aside className="w-72 bg-[#080d1a] border-r border-slate-800 flex flex-col justify-between shrink-0 h-screen sticky top-0 z-30">
        <div className="p-4 flex flex-col gap-4 overflow-y-auto">
          {/* Brand & Title */}
          <div className="flex items-center gap-3 px-2 py-1">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-500 via-indigo-600 to-cyan-400 flex items-center justify-center text-white shadow-md shadow-sky-500/20 shrink-0">
              <Shield className="w-5 h-5 stroke-[2.3]" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-extrabold tracking-tight text-white">ApexMotion</span>
                <span className="px-1.5 py-0.2 rounded text-[9px] font-bold uppercase bg-sky-500/10 text-sky-400 border border-sky-500/20">
                  PROD
                </span>
              </div>
              <p className="text-[10px] text-slate-400 font-medium">Risk &amp; Governance Platform</p>
            </div>
          </div>

          {/* Back to Landing Link */}
          <button
            type="button"
            onClick={() => setActiveView('landing')}
            className="w-full text-left px-3 py-2 rounded-lg text-xs font-semibold text-slate-300 hover:text-white bg-slate-900/60 hover:bg-slate-800 border border-slate-800 transition-all flex items-center gap-2 group"
          >
            <Home className="w-4 h-4 text-sky-400 group-hover:scale-110 transition-transform" />
            <span>← Overview &amp; Blueprint</span>
          </button>

          {/* Navigation List */}
          <div className="flex flex-col gap-1 pt-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 px-3 pb-1">
              Workbench Modules
            </span>
            {NAV_ITEMS.filter(item => item.id !== 'landing').map(item => {
              const Icon = item.icon;
              const isActive = activeView === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveView(item.id)}
                  className={`w-full text-left px-3 py-2.5 rounded-xl text-xs font-semibold transition-all flex items-start gap-3 ${
                    isActive
                      ? 'bg-sky-600 text-white shadow-lg shadow-sky-600/20 font-bold'
                      : 'text-slate-400 hover:text-white hover:bg-slate-900/80'
                  }`}
                >
                  <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="truncate">{item.label}</span>
                      {item.badge && (
                        <span className={`text-[9px] px-1.5 py-0.2 rounded font-mono uppercase ${
                          isActive ? 'bg-white/20 text-white' : 'bg-slate-800 text-sky-400 border border-slate-700'
                        }`}>
                          {item.badge}
                        </span>
                      )}
                    </div>
                    <p className={`text-[10px] truncate mt-0.5 ${isActive ? 'text-sky-100' : 'text-slate-500'}`}>
                      {item.desc}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Bottom Triad Invariants Box */}
        <div className="p-4 border-t border-slate-800/80 bg-[#060a14]">
          <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col gap-2 text-[10px] font-mono">
            <div className="flex items-center justify-between text-slate-400">
              <span>Triad Governance:</span>
              <span className="text-emerald-400 font-semibold flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> Active
              </span>
            </div>
            <div className="space-y-1 text-slate-300">
              <div className="flex items-center gap-1.5">
                <Activity className="w-3 h-3 text-emerald-400" />
                <span>100% Python Risk Math</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Lock className="w-3 h-3 text-sky-400" />
                <span>KMS ECDSA P-256 Spend Gating</span>
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 min-w-0 overflow-y-auto">
        {activeView === 'dashboard' ? (
          <RiskDashboardPage onNavigateToInvestigation={() => setActiveView('investigation')} />
        ) : activeView === 'graph' ? (
          <SupplierGraphPage
            onNavigateToInvestigation={() => setActiveView('investigation')}
            onBackToDashboard={() => setActiveView('dashboard')}
          />
        ) : activeView === 'investigation' ? (
          <InvestigationPage onBackToDashboard={() => setActiveView('dashboard')} />
        ) : activeView === 'approvals' ? (
          <main className="p-6 max-w-[1720px] w-full mx-auto space-y-6">
            <ApprovalQueueTable />
          </main>
        ) : (
          <AuditTrailPage
            onBackToDashboard={() => setActiveView('dashboard')}
            onNavigateToInvestigation={() => setActiveView('investigation')}
            onNavigateToApprovals={() => setActiveView('approvals')}
          />
        )}
      </div>

      {/* Global HITL Spend Authorization Modal */}
      <HITLApprovalModal />
    </div>
  );
};

export default App;
