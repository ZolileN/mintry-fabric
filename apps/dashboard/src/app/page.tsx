"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import StatusHero from '@/components/StatusHero';
import BudgetEditor from '@/components/BudgetEditor';
import AgentLedger from '@/components/AgentLedger';
import ActivityPanel from '@/components/ActivityPanel';
import AdvancedTools from '@/components/AdvancedTools';
import { EMPTY_DASHBOARD, type AttentionItem, type DashboardData } from '@/lib/dashboard-types';
import { money, relativeTime } from '@/lib/format';

const POLL_INTERVAL_MS = 5000;

function SessionBadge() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [method, setMethod] = useState<string>('none');

  useEffect(() => {
    fetch('/api/auth/me')
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!j) return;
        setEmail(j.email || null);
        setMethod(j.method || 'none');
      })
      .catch(() => undefined);
  }, []);

  const signOut = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
    router.refresh();
  };

  if (method === 'none') {
    return <a href="/login" className="nav-pill nav-link">Sign in</a>;
  }

  return (
    <div className="nav-session">
      <span className="nav-email">{email || method}</span>
      <button type="button" className="btn" onClick={signOut}>Sign out</button>
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData>(EMPTY_DASHBOARD);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  // Ticked with the poll so "checked 3 seconds ago" stays honest without
  // reading the clock during render.
  const [now, setNow] = useState<number>(() => Date.now());
  const [focusMandateId, setFocusMandateId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ text: string; type: string } | null>(null);
  const mounted = useRef(true);

  const fetchSummary = useCallback(async () => {
    try {
      const response = await fetch('/api/summary');
      if (!response.ok) throw new Error(`Ledger returned ${response.status}`);
      const json = await response.json();
      if (!mounted.current) return;
      setData(json);
      setError(null);
      setLastUpdated(Date.now());
    } catch (err) {
      if (!mounted.current) return;
      setError(err instanceof Error ? err.message : 'Could not load your ledger');
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const tick = () => {
      setNow(Date.now());
      fetchSummary();
    };
    const initial = setTimeout(tick, 0);
    const interval = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      mounted.current = false;
      clearTimeout(initial);
      clearInterval(interval);
    };
  }, [fetchSummary]);

  const showToast = (text: string, type: string) => {
    setToast({ text, type });
    setTimeout(() => setToast(null), 5000);
  };

  const localGovernance = data.governance?.local_governance ?? true;

  const jumpToBudget = (mandateId: string) => {
    setFocusMandateId(mandateId);
    // Re-arm so clicking the same agent twice scrolls again.
    setTimeout(() => setFocusMandateId(null), 800);
  };

  const handleFix = (item: AttentionItem) => {
    if (item.mandate_id) jumpToBudget(item.mandate_id);
  };

  const stopSpend = async (mandateId: string) => {
    try {
      const res = await fetch('/api/mandates/revoke', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: mandateId }),
      });
      const json = await res.json();
      if (!json.success) throw new Error(json.error || 'Could not stop this agent');
      showToast(`${mandateId} will stop spending immediately.`, 'success');
      fetchSummary();
    } catch (err) {
      showToast(err instanceof Error ? err.message : String(err), 'error');
    }
  };

  const knownAgents = useMemo(() => data.mandates.map((m) => m.id), [data.mandates]);

  const stale = lastUpdated != null && now - lastUpdated > POLL_INTERVAL_MS * 4;
  const sync = data.policy_sync;

  return (
    <>
      <div className="grid-bg" />

      <nav className="nav-header">
        <a href="https://mintry-page.vercel.app/" className="nav-logo">MINTRY <span>.FABRIC</span></a>
        <div className="nav-right">
          <SessionBadge />
        </div>
      </nav>

      <main className="dashboard-container">
        <StatusHero
          attention={data.attention}
          notices={data.budget_notices ?? []}
          loading={loading}
          error={error}
          lastUpdated={lastUpdated}
          now={now}
          onFix={handleFix}
        />

        <section className="summary-strip" aria-label="Spend summary">
          <div className="summary-item">
            <span className="summary-label">Spent so far</span>
            <span className="summary-value">{money(data.stats.total_spent)}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Of a ceiling of</span>
            <span className="summary-value">{money(data.stats.total_budget)}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Requests blocked at the cap</span>
            <span className="summary-value">{data.stats.requests_blocked ?? 0}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Agents reporting</span>
            <span className="summary-value">{data.mandates.length}</span>
          </div>
        </section>

        <div className="bento-grid">
          <BudgetEditor
            mandates={data.mandates}
            governance={data.governance}
            focusMandateId={focusMandateId}
            onSaved={fetchSummary}
          />
        </div>

        <div className="bento-grid">
          <AgentLedger
            mandates={data.mandates}
            policySync={sync}
            hasExpiry={data.has_expiry}
            localGovernance={localGovernance}
            onAdjust={jumpToBudget}
            onPause={stopSpend}
          />
        </div>

        <div className="bento-grid">
          <ActivityPanel history={data.history} />
        </div>

        <div className="bento-grid">
          <AdvancedTools knownAgents={knownAgents} onSaved={fetchSummary} />
        </div>

        <footer className="dashboard-footer">
          <span>
            Enforcement runs on your infrastructure. This page is a read-out — closing it
            changes nothing.
          </span>
          <span className="footer-sync">
            {sync?.last_sync_error
              ? `Policy delivery failing: ${sync.last_sync_error}`
              : sync?.last_synced_at
                ? `Policy last delivered ${relativeTime(sync.last_synced_at, now)}${sync.policy_version != null ? ` (v${sync.policy_version})` : ''}`
                : 'Policy delivery not configured — budgets apply from this host\u2019s ledger'}
            {stale ? ' · this page is not refreshing' : ''}
          </span>
        </footer>
      </main>

      {toast ? (
        <div className={`toast toast-${toast.type}`} role="status">{toast.text}</div>
      ) : null}
    </>
  );
}
