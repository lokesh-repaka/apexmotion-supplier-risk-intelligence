import React, { useState } from 'react';
import { HITLApprovalModal } from './components/HITLApprovalModal/HITLApprovalModal';
import { ApprovalQueueTable } from './components/HITLApprovalModal/ApprovalQueueTable';
import { InvestigationPage } from './pages/InvestigationPage';
import { RiskDashboardPage } from './pages/RiskDashboardPage';
import { SupplierGraphPage } from './pages/SupplierGraphPage';
import { AuditTrailPage } from './pages/AuditTrailPage';

export type AppView = 'dashboard' | 'graph' | 'investigation' | 'approvals' | 'audit';

export const App: React.FC = () => {
  const [activeView, setActiveView] = useState<AppView>('dashboard');

  return (
    <div className="min-h-screen bg-[#060911] text-slate-100 flex flex-col font-sans">
      {/* View Switcher Bar */}
      <nav className="bg-[#080d1a] border-b border-slate-800 px-6 py-2 flex items-center justify-between text-xs sticky top-0 z-40">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setActiveView('dashboard')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition-colors ${
              activeView === 'dashboard'
                ? 'bg-sky-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            Operational Risk Dashboard
          </button>
          <button
            type="button"
            onClick={() => setActiveView('graph')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition-colors ${
              activeView === 'graph'
                ? 'bg-sky-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            Multi-Tier Knowledge Graph
          </button>
          <button
            type="button"
            onClick={() => setActiveView('investigation')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition-colors ${
              activeView === 'investigation'
                ? 'bg-sky-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            Investigation Case Dossier
          </button>
          <button
            type="button"
            onClick={() => setActiveView('approvals')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition-colors ${
              activeView === 'approvals'
                ? 'bg-sky-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            HITL Spend Approvals
          </button>
          <button
            type="button"
            onClick={() => setActiveView('audit')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition-colors ${
              activeView === 'audit'
                ? 'bg-sky-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            WORM Audit Ledger
          </button>
        </div>

        <div className="hidden md:flex items-center gap-2 text-[11px] font-mono text-slate-400">
          <span>Triad Invariant:</span>
          <span className="text-emerald-400 font-semibold">100% Python Risk Math</span>
          <span className="text-slate-600">&bull;</span>
          <span className="text-sky-400 font-semibold">KMS ECDSA P-256 HITL Spend Gating</span>
        </div>
      </nav>

      {/* View Content */}
      <div className="flex-1">
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

