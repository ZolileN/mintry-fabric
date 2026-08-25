"use client";

import React, { useEffect, useState, useCallback } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { useRouter } from 'next/navigation';

function SessionBadge() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [method, setMethod] = useState<string>("none");

  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!j) return;
        setEmail(j.email || null);
        setMethod(j.method || "none");
      })
      .catch(() => undefined);
  }, []);

  const signOut = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  };

  if (method === "none") {
    return (
      <a href="/login" className="nav-pill" style={{ textDecoration: "none" }}>
        Sign in
      </a>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-secondary)" }}>
        {email || method}
      </span>
      <button type="button" className="btn" onClick={signOut} style={{ fontSize: "11px" }}>
        Sign out
      </button>
    </div>
  );
}

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

interface Mandate {
  id: string;
  agent_id?: string;
  status: string;
  budget_usd: number;
  spent_usd: number;
  expires_at: string | null;
  remaining_headroom?: number;
  policy_version?: number | null;
}
interface AgentGroup {
  agent_id: string;
  mandates: Mandate[];
  budget_usd: number;
  spent_usd: number;
  policy_version: number | null;
}
interface LogEvent { action: string; timestamp: string; mandate_id: string; details?: string; amount?: number; }
interface TopMandate { id: string; spent_usd: number; }
interface DashboardStats {
  total_budget: number;
  total_spent: number;
  remaining_headroom: number;
  protected_spend: number;
  requests_blocked: number;
  overspend_prevented: number;
  active_agents: number;
}
interface PolicySync {
  policy_version: number | null;
  last_synced_at: string | null;
  last_sync_error: string | null;
  control_plane_healthy: boolean;
  control_plane_configured?: boolean;
  local_mode?: boolean;
}
interface Governance {
  control_plane_configured: boolean;
  local_governance: boolean;
  authoring_mode: string;
}
interface DashboardData {
  stats: DashboardStats;
  mandates: Mandate[];
  top_mandates: TopMandate[];
  history: LogEvent[];
  has_expiry?: boolean;
  policy_sync?: PolicySync;
  governance?: Governance;
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData>({
    stats: {
      total_budget: 0,
      total_spent: 0,
      remaining_headroom: 0,
      protected_spend: 0,
      requests_blocked: 0,
      overspend_prevented: 0,
      active_agents: 0,
    },
    mandates: [],
    top_mandates: [],
    history: [],
    has_expiry: false,
    policy_sync: {
      policy_version: null,
      last_synced_at: null,
      last_sync_error: null,
      control_plane_healthy: false,
    },
    governance: {
      control_plane_configured: false,
      local_governance: true,
      authoring_mode: 'local_ledger',
    },
  });

  const [formState, setFormState] = useState({ id: '', budget: '', expiry: '' });
  const [simpleBudgetForm, setSimpleBudgetForm] = useState({
    agentId: '',
    monthlyCap: '',
    allow: true,
  });
  const [showAdvancedPolicy, setShowAdvancedPolicy] = useState(false);
  const [feedback, setFeedback] = useState({ text: '', type: '' });
  const [policyForm, setPolicyForm] = useState({
    agentId: '',
    policyJson: '{\n  "customer_support_agent": { "max_usd": 50.0, "allow": true }\n}',
  });
  const [policyFeedback, setPolicyFeedback] = useState({ text: '', type: '' });
  const [fleetForm, setFleetForm] = useState({
    fleetId: '',
    totalUsd: '',
    partitionsJson: '{\n  "agent_a": 40.0,\n  "agent_b": 60.0\n}',
  });
  const [fleetFeedback, setFleetFeedback] = useState({ text: '', type: '' });
  const [orgForm, setOrgForm] = useState({
    fleetId: 'acme-fleet',
    orgJson: JSON.stringify({
      id: 'acme',
      kind: 'company',
      budget_usd: 1000,
      children: [{
        id: 'eng',
        kind: 'department',
        budget_usd: 600,
        children: [
          { id: 'agent_a', kind: 'agent', budget_usd: 400 },
          { id: 'agent_b', kind: 'agent' },
        ],
      }, {
        id: 'sales',
        kind: 'department',
        budget_usd: 400,
        children: [{ id: 'agent_c', kind: 'agent' }],
      }],
    }, null, 2),
  });
  const [orgFeedback, setOrgFeedback] = useState({ text: '', type: '' });
  const [secretForm, setSecretForm] = useState({
    aliasesJson: '[\n  {"alias": "OPENAI_PROD_KEY", "provider": "openai"}\n]',
  });
  const [secretFeedback, setSecretFeedback] = useState({ text: '', type: '' });

  const fetchSummary = useCallback(async () => {
    try {
      const response = await fetch('/api/summary');
      if (response.ok) {
        const json = await response.json();
        setData(json);
      }
    } catch (error) {
      console.error("Dashboard API sync failed:", error);
    }
  }, []);

  useEffect(() => {
    fetch('/api/summary')
      .then(res => res.ok ? res.json() : Promise.reject('Not OK'))
      .then(json => setData(json))
      .catch(err => console.error("Dashboard API sync failed:", err));

    const interval = setInterval(fetchSummary, 5000);
    return () => clearInterval(interval);
  }, [fetchSummary]);

  const handleUpsert = async (e: React.FormEvent) => {
    e.preventDefault();
    let expires_at = null;
    if (formState.expiry) {
        expires_at = new Date(formState.expiry).toISOString();
    }

    try {
        const res = await fetch('/api/mandates/upsert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: formState.id, budget_usd: parseFloat(formState.budget), expires_at })
        });
        const json = await res.json();
        if (json.success) {
            showFeedback("Agent mandate allocated successfully", "success");
            setFormState({ id: '', budget: '', expiry: '' });
            fetchSummary();
        } else {
            showFeedback(json.error || "Allocation failed", "error");
        }
    } catch {
        showFeedback("Connection error", "error");
    }
  };
  const handlePushPolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      let parsedJson;
      try {
        parsedJson = JSON.parse(policyForm.policyJson);
      } catch {
        setPolicyFeedback({ text: 'Invalid JSON format', type: 'error' });
        setTimeout(() => setPolicyFeedback({ text: '', type: '' }), 4000);
        return;
      }

      const res = await fetch('/api/policies/sign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: policyForm.agentId, mandates: parsedJson })
      });
      
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Failed to push policy');
      
      setPolicyFeedback({ text: `Policy v${json.version} pushed successfully`, type: 'success' });
      setPolicyForm({
        agentId: '',
        policyJson: '{\n  "customer_support_agent": { "max_usd": 50.0, "allow": true }\n}',
      });
      fetchSummary();
    } catch (err: unknown) {
      setPolicyFeedback({ text: err instanceof Error ? err.message : String(err), type: 'error' });
    }
    setTimeout(() => setPolicyFeedback({ text: '', type: '' }), 12000);
  };

  const handleFleetPartition = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      let partitions: Record<string, number>;
      try {
        partitions = JSON.parse(fleetForm.partitionsJson);
      } catch {
        setFleetFeedback({ text: 'Invalid partitions JSON', type: 'error' });
        setTimeout(() => setFleetFeedback({ text: '', type: '' }), 4000);
        return;
      }

      const res = await fetch('/api/fleets/partition', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fleet_id: fleetForm.fleetId,
          total_usd: parseFloat(fleetForm.totalUsd),
          partitions,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Fleet partition failed');

      const agentSummary = (json.agents || [])
        .map((a: { agent_id: string; version: number; share_usd: number }) =>
          `${a.agent_id}@v${a.version}=$${a.share_usd}`
        )
        .join(', ');
      setFleetFeedback({
        text: `Fleet ${json.fleet_id}: pushed ${json.agents?.length || 0} agents (${agentSummary})`,
        type: 'success',
      });
      setFleetForm({
        fleetId: '',
        totalUsd: '',
        partitionsJson: '{\n  "agent_a": 40.0,\n  "agent_b": 60.0\n}',
      });
      fetchSummary();
    } catch (err: unknown) {
      setFleetFeedback({
        text: err instanceof Error ? err.message : String(err),
        type: 'error',
      });
    }
    setTimeout(() => setFleetFeedback({ text: '', type: '' }), 12000);
  };

  const handleOrgCompile = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      let org: unknown;
      try {
        org = JSON.parse(orgForm.orgJson);
      } catch {
        setOrgFeedback({ text: 'Invalid org JSON', type: 'error' });
        setTimeout(() => setOrgFeedback({ text: '', type: '' }), 4000);
        return;
      }
      const res = await fetch('/api/orgs/compile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          org,
          fleet_id: orgForm.fleetId || undefined,
          push: Boolean(orgForm.fleetId),
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Org compile failed');
      const caps = Object.entries(json.agent_caps || {})
        .map(([k, v]) => `${k}=$${v}`)
        .join(', ');
      setOrgFeedback({
        text: `Compiled ${Object.keys(json.agent_caps || {}).length} agents (${caps})` +
          (json.fleet ? ` · fleet pushed` : ''),
        type: 'success',
      });
      fetchSummary();
    } catch (err: unknown) {
      setOrgFeedback({
        text: err instanceof Error ? err.message : String(err),
        type: 'error',
      });
    }
    setTimeout(() => setOrgFeedback({ text: '', type: '' }), 12000);
  };

  const handleSecretAliases = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      let aliases: unknown;
      try {
        aliases = JSON.parse(secretForm.aliasesJson);
      } catch {
        setSecretFeedback({ text: 'Invalid aliases JSON', type: 'error' });
        setTimeout(() => setSecretFeedback({ text: '', type: '' }), 4000);
        return;
      }
      const res = await fetch('/api/secrets/aliases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ aliases }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Alias validation failed');
      setSecretFeedback({
        text: `Validated ${(json.aliases || []).length} alias ref(s) — values stay on customer host`,
        type: 'success',
      });
    } catch (err: unknown) {
      setSecretFeedback({
        text: err instanceof Error ? err.message : String(err),
        type: 'error',
      });
    }
    setTimeout(() => setSecretFeedback({ text: '', type: '' }), 12000);
  };

  const revokeMandate = async (id: string) => {
    if (!confirm(`Revoke budget for agent: ${id}?`)) return;
    try {
        const res = await fetch('/api/mandates/revoke', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        const json = await res.json();
        if (json.success) {
            showFeedback(`Agent ${id} revoked`, "success");
            fetchSummary();
        } else {
            showFeedback(json.error || "Revocation failed", "error");
        }
    } catch {
        showFeedback("Connection error", "error");
    }
  };

  const agentGroups: AgentGroup[] = (() => {
    const map = new Map<string, AgentGroup>();
    for (const m of data.mandates) {
      const agentId = (m.agent_id || m.id || 'unknown').trim() || 'unknown';
      let group = map.get(agentId);
      if (!group) {
        group = {
          agent_id: agentId,
          mandates: [],
          budget_usd: 0,
          spent_usd: 0,
          policy_version: null,
        };
        map.set(agentId, group);
      }
      group.mandates.push(m);
      group.budget_usd += m.budget_usd || 0;
      group.spent_usd += m.spent_usd || 0;
      const pv = m.policy_version ?? null;
      if (pv != null && (group.policy_version == null || pv > group.policy_version)) {
        group.policy_version = pv;
      }
    }
    return Array.from(map.values()).sort((a, b) => a.agent_id.localeCompare(b.agent_id));
  })();

  const showFeedback = (text: string, type: string, persistent = false) => {
    setFeedback({ text, type });
    if (text && !persistent) {
      setTimeout(() => setFeedback({ text: '', type: '' }), 12000);
    }
  };

  const handleSimpleBudget = async (e: React.FormEvent) => {
    e.preventDefault();
    const agentId = simpleBudgetForm.agentId.trim();
    const cap = parseFloat(simpleBudgetForm.monthlyCap);
    if (!agentId || !Number.isFinite(cap) || cap <= 0) {
      setPolicyFeedback({ text: 'Enter an agent name and a positive monthly cap.', type: 'error' });
      return;
    }
    const mandates = {
      [agentId]: { max_usd: cap, allow: simpleBudgetForm.allow },
    };
    try {
      const res = await fetch('/api/policies/sign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId, mandates }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Failed to set budget');
      setPolicyFeedback({
        text: `Budget set for ${agentId}: $${cap.toFixed(2)}/month (policy v${json.version})`,
        type: 'success',
      });
      setSimpleBudgetForm({ agentId: '', monthlyCap: '', allow: true });
      fetchSummary();
    } catch (err: unknown) {
      setPolicyFeedback({
        text: err instanceof Error ? err.message : String(err),
        type: 'error',
      });
    }
  };

  const sortedHistory = [...(data.history || [])].reverse();
  let runningTotal = 0;
  const labels: string[] = [];
  const dataPoints: number[] = [];

  sortedHistory.forEach((log) => {
      if (log.action === 'spend') {
          runningTotal += log.amount || 0;
          const date = new Date(log.timestamp);
          labels.push(date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
          dataPoints.push(runningTotal);
      }
  });

  const maxPoints = 20;
  const slicedLabels = labels.slice(-maxPoints);
  const slicedData = dataPoints.slice(-maxPoints);

  const chartData = {
    labels: slicedLabels,
    datasets: [{
        label: 'Cumulative Spend (USD)',
        data: slicedData,
        borderColor: '#10B981',
        backgroundColor: 'rgba(16, 185, 129, 0.03)',
        borderWidth: 2,
        fill: true,
        tension: 0.2,
        pointBackgroundColor: '#10B981',
        pointBorderColor: '#050505',
        pointBorderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5
    }]
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
        x: { grid: { color: 'rgba(255, 255, 255, 0.03)' }, ticks: { color: '#8a8a8a', font: { family: 'JetBrains Mono', size: 10 } } },
        y: { grid: { color: 'rgba(255, 255, 255, 0.03)' }, ticks: { color: '#8a8a8a', font: { family: 'JetBrains Mono', size: 10 } } }
    }
  };

  const formatExpiry = (expires_at: string | null) => {
    if (!expires_at) return null;
    return new Date(expires_at).toLocaleString();
  };

  const allocatedBudget = data.stats.total_budget || 0;
  const cumulativeSpent = data.stats.total_spent || 0;
  const utilization = allocatedBudget > 0 ? (cumulativeSpent / allocatedBudget) * 100 : 0;
  
  let utilizationStatus = 'Healthy';
  let utilizationColor = 'var(--mint)';
  if (utilization >= 95) {
      utilizationStatus = 'Critical';
      utilizationColor = '#ef4444'; // Red
  } else if (utilization >= 85) {
      utilizationStatus = 'Warning';
      utilizationColor = '#f97316'; // Orange
  } else if (utilization >= 60) {
      utilizationStatus = 'Monitor';
      utilizationColor = '#eab308'; // Amber
  }

  const activeAgents = data.stats.active_agents ?? data.mandates.filter(m => m.status === 'active').length;
  const totalAgents = data.mandates.length;
  const localGovernance = data.governance?.local_governance ?? true;
  const localMode = data.policy_sync?.local_mode ?? !data.governance?.control_plane_configured;
  const controlPlaneHealthy = data.policy_sync?.control_plane_healthy ?? false;

  return (
    <>
      <div className="grid-bg"></div>

      <nav className="nav-header">
        <a href="https://mintry-page.vercel.app/" className="nav-logo">MINTRY <span>.FABRIC</span></a>
        <div style={{display:'flex', alignItems:'center', gap:'0.75rem'}}>
          <SessionBadge />
          <div className="nav-pill">
              <div className="pulse-dot"></div>
              v1.1 Observatory
          </div>
        </div>
      </nav>

      <div className="dashboard-container">

        {data.mandates.length === 0 && (
          <div className="bento-card col-12" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
            <h2 style={{ margin: '0 0 0.5rem', fontSize: '1.1rem' }}>Welcome — set up in one step</h2>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-secondary)', margin: '0 0 0.75rem' }}>
              Add Mintry once in your app, then set a monthly cap below. Spend is enforced locally — no per-request headers required when using <code>mintry.mandate()</code>.
            </p>
            <pre style={{
              fontFamily: 'var(--font-mono)', fontSize: '11px', background: 'var(--glass)',
              padding: '0.75rem', borderRadius: '6px', overflow: 'auto', margin: 0,
            }}>
{`import mintry
mintry.init(api_key="mk_…", db_path="~/.mintry/vouchers.db")

with mintry.mandate("my_agent", cap=50.0):
    client.chat.completions.create(...)  # attributed automatically`}
            </pre>
          </div>
        )}

        <div className="section-label mint">{"// 01 — Spend overview"}</div>

        <div className="kpi-grid">
            <div className="bento-card kpi-card kpi-card-wide">
                <div className="kpi-label">Tracked Spend</div>
                <div className="kpi-value mint">${(data.stats.protected_spend ?? data.stats.total_spent ?? 0).toFixed(4)}</div>
            </div>
            <div className="bento-card kpi-card kpi-card-wide">
                <div className="kpi-label">Allocated Budget</div>
                <div className="kpi-value">${(data.stats.total_budget ?? 0).toFixed(4)}</div>
            </div>
            <div className="bento-card kpi-card">
                <div className="kpi-label">Requests Blocked</div>
                <div className="kpi-value amber">{data.stats.requests_blocked ?? 0}</div>
            </div>
            <div className="bento-card kpi-card">
                <div className="kpi-label">Overspend Prevented</div>
                <div className="kpi-value">${(data.stats.overspend_prevented ?? 0).toFixed(4)}</div>
            </div>
            <div className="bento-card kpi-card">
                <div className="kpi-label">Budget Utilization</div>
                <div className="kpi-value">{utilization.toFixed(0)}%</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px', fontFamily: 'var(--font-mono)' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: utilizationColor }}></div>
                    {utilizationStatus}
                </div>
            </div>
            <div className="bento-card kpi-card">
                <div className="kpi-label">Active Agents</div>
                <div className="kpi-value">{activeAgents} / {totalAgents}</div>
            </div>
        </div>

        <div className="section-label mint">{"// 02 — Activity feed"}</div>

        <div className="bento-grid">
            <div className="bento-card col-12">
                <div className="panel-header">
                    <h2>Activity Feed</h2>
                    <span style={{fontFamily:'var(--font-mono)', fontSize:'11px', color:'var(--text-tertiary)'}}>ALLOW · BLOCK · SPEND</span>
                </div>
                <div className="event-list" style={{maxHeight: '320px'}}>
                    {data.history.length === 0 ? (
                      <p style={{color:'var(--text-tertiary)', fontFamily:'var(--font-mono)', textAlign:'center', paddingTop:'3rem', fontSize:'12px'}}>{"// No enforcement events yet"}</p>
                    ) : (
                      data.history.map((log, i: number) => (
                        <div key={i} className="event-item">
                          <div className="event-header">
                              <span className={`event-action ${log.action}`}>{log.action.replace('_', ' ')}</span>
                              <span className="event-time">{new Date(log.timestamp).toLocaleTimeString()}</span>
                          </div>
                          <div className="event-body">
                              <code>{log.mandate_id}</code>: {log.details || ""}
                              {typeof log.amount === 'number' && log.amount !== 0 ? (
                                <span style={{marginLeft:'0.5rem', color:'var(--text-secondary)'}}>${log.amount.toFixed(4)}</span>
                              ) : null}
                          </div>
                        </div>
                      ))
                    )}
                </div>
            </div>
        </div>

        <div className="section-label">{"// 03 — Spend charts"}</div>

        <div className="bento-grid">
            <div className="bento-card col-8">
                <div className="panel-header">
                    <h2>Spend Over Time</h2>
                </div>
                <div className="chart-container">
                  {slicedLabels.length > 0 ? (
                    <Line data={chartData} options={chartOptions as unknown as object} />
                  ) : (
                    <div style={{color:'var(--text-tertiary)', fontFamily:'var(--font-mono)', textAlign:'center', paddingTop:'4rem', fontSize:'12px'}}>{"// No consumption data"}</div>
                  )}
                </div>
            </div>
            <div className="bento-card col-4">
                <div className="panel-header">
                    <h2>Top Consumers</h2>
                </div>
                <div className="top-mandate-list">
                    {data.top_mandates.length === 0 ? (
                      <p style={{color:'var(--text-tertiary)', fontFamily:'var(--font-mono)', textAlign:'center', paddingTop:'4rem', fontSize:'12px'}}>{"// No consumption data"}</p>
                    ) : (
                      data.top_mandates.map((m, i: number) => {
                        const fullMandate = data.mandates.find((md) => md.id === m.id) || {budget_usd: 0.01};
                        const percent = fullMandate.budget_usd > 0 ? (m.spent_usd / fullMandate.budget_usd) * 100 : 0;
                        return (
                          <div key={i} className="top-mandate-item">
                            <div className="top-mandate-meta">
                                <span className="top-mandate-id">{m.id}</span>
                                <span className="top-mandate-spent">${m.spent_usd.toFixed(4)}</span>
                            </div>
                            <div className="progress-bar-container">
                                <div className="progress-bar-fill" style={{width: `${Math.min(percent, 100)}%`}}></div>
                            </div>
                          </div>
                        )
                      })
                    )}
                </div>
            </div>
        </div>

        {/* 04 — Sync status */}
        <div className="section-label mint">{"// 04 — Policy sync"}</div>
        <div className="bento-grid" style={{marginBottom: '1.5rem'}}>
          <div className="bento-card col-12">
            <div className="panel-header">
              <h2>Sync Status</h2>
              {localMode && (
                <span style={{fontFamily:'var(--font-mono)', fontSize:'10px', color:'var(--mint)'}}>
                  local mode — budgets apply from this host
                </span>
              )}
            </div>
            <div style={{display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:'1.5rem', padding:'0.5rem 0'}}>
              <div style={{display:'flex', flexDirection:'column', gap:'0.4rem'}}>
                <span style={{fontFamily:'var(--font-mono)', fontSize:'10px', color:'var(--text-tertiary)', textTransform:'uppercase', letterSpacing:'0.08em'}}>policy version</span>
                <span style={{fontFamily:'var(--font-mono)', fontSize:'1.6rem', fontWeight:700, color: data.policy_sync?.policy_version != null ? 'var(--mint)' : 'var(--text-tertiary)'}}>
                  {data.policy_sync?.policy_version != null ? `v${data.policy_sync.policy_version}` : '—'}
                </span>
              </div>
              {/* last_synced_at */}
              <div style={{display:'flex', flexDirection:'column', gap:'0.4rem'}}>
                <span style={{fontFamily:'var(--font-mono)', fontSize:'10px', color:'var(--text-tertiary)', textTransform:'uppercase', letterSpacing:'0.08em'}}>last_synced_at</span>
                <span style={{fontFamily:'var(--font-mono)', fontSize:'13px', color: data.policy_sync?.last_synced_at ? 'var(--text-primary)' : 'var(--text-tertiary)', wordBreak:'break-all'}}>
                  {data.policy_sync?.last_synced_at
                    ? new Date(data.policy_sync.last_synced_at).toLocaleString()
                    : '—'}
                </span>
                {data.policy_sync?.last_sync_error && (
                  <span style={{fontFamily:'var(--font-mono)', fontSize:'11px', color:'var(--amber)', marginTop:'0.2rem'}}>
                    ⚠ {data.policy_sync.last_sync_error}
                  </span>
                )}
              </div>
              <div style={{display:'flex', flexDirection:'column', gap:'0.4rem'}}>
                <span style={{fontFamily:'var(--font-mono)', fontSize:'10px', color:'var(--text-tertiary)', textTransform:'uppercase', letterSpacing:'0.08em'}}>sync health</span>
                <div style={{display:'flex', alignItems:'center', gap:'0.5rem', marginTop:'0.2rem'}}>
                  <div style={{
                    width:'10px', height:'10px', borderRadius:'50%',
                    background: localMode ? '#10B981' : (controlPlaneHealthy ? '#10B981' : '#EF4444'),
                    boxShadow: localMode ? '0 0 8px #10B981' : (controlPlaneHealthy ? '0 0 8px #10B981' : '0 0 8px #EF4444'),
                    flexShrink: 0,
                  }} />
                  <span style={{fontFamily:'var(--font-mono)', fontSize:'13px', fontWeight:600,
                    color: localMode ? 'var(--mint)' : (controlPlaneHealthy ? 'var(--mint)' : '#EF4444')}}>
                    {localMode ? 'local (healthy)' : (controlPlaneHealthy ? 'connected' : 'unreachable')}
                  </span>
                </div>
                {localMode && (
                  <span style={{fontFamily:'var(--font-mono)', fontSize:'11px', color:'var(--text-tertiary)', marginTop:'0.2rem'}}>
                    No cloud control plane configured — enforcement uses this machine&apos;s ledger and signed policies when available.
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="section-label">{"// 05 — Agents & budgets"}</div>

        <div className="bento-grid">
            <div className="bento-card col-8">
                <div className="panel-header">
                    <h2>Agent Budgets</h2>
                    <span style={{fontFamily:'var(--font-mono)', fontSize:'11px', color:'var(--text-tertiary)'}}>
                      {agentGroups.length} agent{agentGroups.length === 1 ? '' : 's'}
                    </span>
                </div>
                <div className="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Agent / Mandate</th>
                                <th>Status</th>
                                <th>Budget</th>
                                <th>Spent</th>
                                <th>Remaining</th>
                                <th>Policy Version</th>
                                {data.has_expiry && <th>Expiry</th>}
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {agentGroups.length === 0 ? (
                              <tr><td colSpan={data.has_expiry ? 8 : 7} style={{textAlign:'center', color:'var(--text-tertiary)', fontFamily:'var(--font-mono)', fontSize:'12px'}}>{"// Mandate ledger empty"}</td></tr>
                            ) : (
                              agentGroups.flatMap((group) => {
                                const groupRemaining = group.budget_usd - group.spent_usd;
                                const header = (
                                  <tr key={`g-${group.agent_id}`} style={{background:'rgba(255,255,255,0.03)'}}>
                                    <td className="td-id" colSpan={2} style={{fontWeight:600}}>
                                      {group.agent_id}
                                      <span style={{marginLeft:'0.5rem', fontWeight:400, color:'var(--text-tertiary)', fontSize:'11px'}}>
                                        {group.mandates.length} mandate{group.mandates.length === 1 ? '' : 's'}
                                      </span>
                                    </td>
                                    <td style={{fontFamily:'var(--font-mono)', fontSize:'12px'}}>${group.budget_usd.toFixed(4)}</td>
                                    <td style={{fontFamily:'var(--font-mono)', fontSize:'12px'}}>${group.spent_usd.toFixed(4)}</td>
                                    <td style={{fontFamily:'var(--font-mono)', fontSize:'12px'}}>${groupRemaining.toFixed(4)}</td>
                                    <td>
                                      <span className="badge" style={{background: 'rgba(16,185,129,0.12)', color: 'var(--mint)'}}>
                                        v{group.policy_version ?? data.policy_sync?.policy_version ?? '—'}
                                      </span>
                                    </td>
                                    {data.has_expiry && <td />}
                                    <td />
                                  </tr>
                                );
                                const rows = group.mandates.map((m, i: number) => {
                                  let badgeClass = 'badge-active';
                                  if (m.status === 'exhausted') badgeClass = 'badge-exhausted';
                                  if (m.status === 'expired') badgeClass = 'badge-expired';
                                  const remaining = typeof m.remaining_headroom === 'number'
                                      ? m.remaining_headroom
                                      : ((m.budget_usd || 0) - (m.spent_usd || 0));

                                  return (
                                    <tr key={`${group.agent_id}-${m.id}-${i}`}>
                                        <td className="td-id" style={{paddingLeft:'1.5rem', color:'var(--text-secondary)'}}>{m.id}</td>
                                        <td><span className={`badge ${badgeClass}`}>{m.status}</span></td>
                                        <td>${m.budget_usd.toFixed(4)}</td>
                                        <td>${m.spent_usd.toFixed(4)}</td>
                                        <td>${remaining.toFixed(4)}</td>
                                        <td>
                                            <span className="badge" style={{background: 'rgba(255,255,255,0.05)', color: '#8a8a8a'}}>
                                                v{m.policy_version || data.policy_sync?.policy_version || '—'}
                                            </span>
                                        </td>
                                        {data.has_expiry && (
                                          <td style={{color:'var(--text-secondary)', fontFamily:'var(--font-mono)', fontSize:'11px'}}>
                                            {formatExpiry(m.expires_at) ?? '—'}
                                          </td>
                                        )}
                                        <td>
                                            {localGovernance ? (
                                              <>
                                                <button className="btn btn-danger" onClick={() => revokeMandate(m.id)}>Revoke</button>
                                                <button className="btn" onClick={() => {
                                                  setFormState({ id: m.id, budget: m.budget_usd.toString(), expiry: '' });
                                                }}>Top-up</button>
                                              </>
                                            ) : (
                                              <span style={{fontFamily:'var(--font-mono)', fontSize:'10px', color:'var(--text-tertiary)'}}>
                                                via Sign &amp; Push
                                              </span>
                                            )}
                                        </td>
                                    </tr>
                                  );
                                });
                                return [header, ...rows];
                              })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
            <div className="bento-card col-4">
                <div className="panel-header">
                    <h2>Set Agent Budget</h2>
                    <span style={{fontFamily:'var(--font-mono)', fontSize:'10px', color:'var(--mint)'}}>
                      {data.governance?.authoring_mode === 'central_sign_and_push'
                        ? 'source of truth'
                        : data.governance?.control_plane_configured
                          ? 'central + local opt-in'
                          : 'local-only agent'}
                    </span>
                </div>
                <p style={{fontFamily:'var(--font-mono)', fontSize:'11px', color:'var(--text-tertiary)', margin:'0 0 0.75rem'}}>
                  Set a monthly cap — signed policies sync to agents in the background. No per-request work for your team.
                </p>
                <form onSubmit={handleSimpleBudget} style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="simple-agent-id">Agent name</label>
                        <input type="text" id="simple-agent-id" required placeholder="e.g. customer_support_agent" className="form-input" value={simpleBudgetForm.agentId} onChange={e => setSimpleBudgetForm({...simpleBudgetForm, agentId: e.target.value})} />
                    </div>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="simple-monthly-cap">Monthly cap (USD)</label>
                        <input type="number" id="simple-monthly-cap" required step="0.01" min="0.01" placeholder="e.g. 50.00" className="form-input" value={simpleBudgetForm.monthlyCap} onChange={e => setSimpleBudgetForm({...simpleBudgetForm, monthlyCap: e.target.value})} />
                    </div>
                    <label style={{display:'flex', alignItems:'center', gap:'0.5rem', fontFamily:'var(--font-mono)', fontSize:'12px'}}>
                      <input type="checkbox" checked={simpleBudgetForm.allow} onChange={e => setSimpleBudgetForm({...simpleBudgetForm, allow: e.target.checked})} />
                      Allow requests (block when unchecked)
                    </label>
                    <button type="submit" className="btn-submit" style={{background: 'var(--mint)', color: '#050505'}}>Set budget &amp; push policy</button>
                </form>

                <button type="button" className="btn" style={{ marginTop: '1rem', fontSize: '11px' }} onClick={() => setShowAdvancedPolicy(v => !v)}>
                  {showAdvancedPolicy ? 'Hide advanced JSON' : 'Advanced JSON editor'}
                </button>

                {showAdvancedPolicy && (
                <form onSubmit={handlePushPolicy} style={{display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem'}}>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="policy-agent-id">Agent ID</label>
                        <input type="text" id="policy-agent-id" required placeholder="e.g. customer_support_agent" className="form-input" value={policyForm.agentId} onChange={e => setPolicyForm({...policyForm, agentId: e.target.value})} />
                    </div>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="policy-json">Budget rules JSON</label>
                        <textarea id="policy-json" required rows={5} placeholder='{"customer_support_agent": {"max_usd": 50.0, "allow": true}}' className="form-input" style={{fontFamily: 'var(--font-mono)', fontSize: '11px', resize: 'vertical'}} value={policyForm.policyJson} onChange={e => setPolicyForm({...policyForm, policyJson: e.target.value})} />
                    </div>
                    <button type="submit" className="btn-submit" style={{background: 'var(--blue)'}}>Sign &amp; Push vNext</button>
                </form>
                )}
                {policyFeedback.text && (
                  <div className={`feedback-message ${policyFeedback.type}`} style={{ marginTop: '0.75rem' }}>
                    {policyFeedback.text}
                    <button type="button" className="btn" style={{ marginLeft: '0.5rem', fontSize: '10px' }} onClick={() => setPolicyFeedback({ text: '', type: '' })}>Dismiss</button>
                  </div>
                )}

                <div className="panel-header" style={{ marginTop: '2rem' }}>
                    <h2>Fleet Partition (Option A)</h2>
                </div>
                <p style={{fontFamily:'var(--font-mono)', fontSize:'11px', color:'var(--text-tertiary)', margin:'0 0 0.75rem'}}>
                  Split a fleet total into static per-agent shares. Sum must be ≤ total. Each agent gets a signed policy with its local max_usd.
                </p>
                <form onSubmit={handleFleetPartition} style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="fleet-id">Fleet ID</label>
                        <input type="text" id="fleet-id" required placeholder="e.g. prod-us-east" className="form-input" value={fleetForm.fleetId} onChange={e => setFleetForm({...fleetForm, fleetId: e.target.value})} />
                    </div>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="fleet-total">Fleet Total (USD)</label>
                        <input type="number" id="fleet-total" required step="0.01" min="0.01" placeholder="e.g. 1000.00" className="form-input" value={fleetForm.totalUsd} onChange={e => setFleetForm({...fleetForm, totalUsd: e.target.value})} />
                    </div>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="fleet-partitions">Partitions JSON</label>
                        <textarea id="fleet-partitions" required rows={5} className="form-input" style={{fontFamily: 'var(--font-mono)', fontSize: '11px', resize: 'vertical'}} value={fleetForm.partitionsJson} onChange={e => setFleetForm({...fleetForm, partitionsJson: e.target.value})} />
                    </div>
                    <button type="submit" className="btn-submit" style={{background: 'var(--mint)', color: '#050505'}}>Partition &amp; Push</button>
                    <div className={`feedback-message ${fleetFeedback.type}`}>{fleetFeedback.text}</div>
                </form>

                <div className="panel-header" style={{ marginTop: '2rem' }}>
                    <h2>Org Hierarchy Compile</h2>
                </div>
                <p style={{fontFamily:'var(--font-mono)', fontSize:'11px', color:'var(--text-tertiary)', margin:'0 0 0.75rem'}}>
                  Company → department → project → agent. Inheritance compiles to flat caps; optional fleet push.
                </p>
                <form onSubmit={handleOrgCompile} style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="org-fleet-id">Fleet ID (push when set)</label>
                        <input type="text" id="org-fleet-id" className="form-input" value={orgForm.fleetId} onChange={e => setOrgForm({...orgForm, fleetId: e.target.value})} />
                    </div>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="org-json">Org Tree JSON</label>
                        <textarea id="org-json" required rows={8} className="form-input" style={{fontFamily: 'var(--font-mono)', fontSize: '11px', resize: 'vertical'}} value={orgForm.orgJson} onChange={e => setOrgForm({...orgForm, orgJson: e.target.value})} />
                    </div>
                    <button type="submit" className="btn-submit">Compile &amp; Push Fleet</button>
                    <div className={`feedback-message ${orgFeedback.type}`}>{orgFeedback.text}</div>
                </form>

                <div className="panel-header" style={{ marginTop: '2rem' }}>
                    <h2>Secret Aliases</h2>
                </div>
                <p style={{fontFamily:'var(--font-mono)', fontSize:'11px', color:'var(--text-tertiary)', margin:'0 0 0.75rem'}}>
                  Alias references only — never paste raw API keys. Agents resolve from env / Vault.
                </p>
                <form onSubmit={handleSecretAliases} style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="secret-aliases">Aliases JSON</label>
                        <textarea id="secret-aliases" required rows={4} className="form-input" style={{fontFamily: 'var(--font-mono)', fontSize: '11px', resize: 'vertical'}} value={secretForm.aliasesJson} onChange={e => setSecretForm({...secretForm, aliasesJson: e.target.value})} />
                    </div>
                    <button type="submit" className="btn-submit" style={{background: 'var(--text-secondary)'}}>Validate Aliases</button>
                    <div className={`feedback-message ${secretFeedback.type}`}>{secretFeedback.text}</div>
                </form>

                <div className="panel-header" style={{ marginTop: '2rem' }}>
                    <h2>Local ledger edits</h2>
                    <span style={{fontFamily:'var(--font-mono)', fontSize:'10px', color:'var(--text-tertiary)'}}>
                      {localGovernance ? 'enabled' : 'gated'}
                    </span>
                </div>
                {!localGovernance ? (
                  <p style={{fontFamily:'var(--font-mono)', fontSize:'11px', color:'var(--amber)', margin:0}}>
                    Control plane configured — caps are authored via Sign &amp; Push above.
                    Set <code>MINTRY_LOCAL_GOVERNANCE=1</code> only for air-gapped / local ledger upserts.
                  </p>
                ) : (
                  <>
                    <p style={{fontFamily:'var(--font-mono)', fontSize:'11px', color:'var(--text-tertiary)', margin:'0 0 0.75rem'}}>
                      Writes directly to this host&apos;s SQLite ledger. Does not create a signed policy version.
                    </p>
                    <form onSubmit={handleUpsert} style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                        <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                            <label className="kpi-label" htmlFor="form-mandate-id">Mandate ID</label>
                            <input type="text" id="form-mandate-id" required placeholder="e.g. customer_support_agent" className="form-input" value={formState.id} onChange={e => setFormState({...formState, id: e.target.value})} />
                        </div>
                        <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                            <label className="kpi-label" htmlFor="form-budget">Budget Limit (USD)</label>
                            <input type="number" id="form-budget" required step="0.0001" min="0.0001" placeholder="e.g. 50.00" className="form-input" value={formState.budget} onChange={e => setFormState({...formState, budget: e.target.value})} />
                        </div>
                        <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                            <label className="kpi-label" htmlFor="form-expiry">Expiry Date (Optional)</label>
                            <input type="datetime-local" id="form-expiry" className="form-input" value={formState.expiry} onChange={e => setFormState({...formState, expiry: e.target.value})} />
                        </div>
                        <button type="submit" className="btn-submit">Apply to local ledger</button>
                        <div className={`feedback-message ${feedback.type}`}>{feedback.text}</div>
                    </form>
                  </>
                )}
            </div>
        </div>
      </div>
    </>
  );
}
