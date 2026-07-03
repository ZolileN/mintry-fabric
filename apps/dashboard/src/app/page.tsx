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

interface Mandate { id: string; status: string; budget_usd: number; spent_usd: number; expires_at: string | null; remaining_headroom?: number; policy_version?: number | null; }
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
}
interface DashboardData {
  stats: DashboardStats;
  mandates: Mandate[];
  top_mandates: TopMandate[];
  history: LogEvent[];
  has_expiry?: boolean;
  policy_sync?: PolicySync;
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
  });

  const [formState, setFormState] = useState({ id: '', budget: '', expiry: '' });
  const [feedback, setFeedback] = useState({ text: '', type: '' });
  const [policyForm, setPolicyForm] = useState({ agentId: '', policyJson: '' });
  const [policyFeedback, setPolicyFeedback] = useState({ text: '', type: '' });

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

    const interval = setInterval(fetchSummary, 3000);
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
      setPolicyForm({ agentId: '', policyJson: '' });
      fetchSummary();
    } catch (err: unknown) {
      setPolicyFeedback({ text: err instanceof Error ? err.message : String(err), type: 'error' });
    }
    setTimeout(() => setPolicyFeedback({ text: '', type: '' }), 4000);
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

  const showFeedback = (text: string, type: string) => {
    setFeedback({ text, type });
    if (text) {
      setTimeout(() => setFeedback({ text: '', type: '' }), 4000);
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

  return (
    <>
      <div className="grid-bg"></div>

      <nav className="nav-header">
        <a href="https://mintry-page.vercel.app/" className="nav-logo">MINTRY <span>.FABRIC</span></a>
        <div className="nav-pill">
            <div className="pulse-dot"></div>
            v1.0.0 Observatory
        </div>
      </nav>

      <div className="dashboard-container">

        <div className="section-label mint">{"// 01 — Governance indicators"}</div>

        <div className="kpi-grid">
            <div className="bento-card kpi-card kpi-card-wide">
                <div className="kpi-label">Allocated Budget</div>
                <div className="kpi-value mint">${(data.stats.total_budget ?? 0).toFixed(4)}</div>
            </div>
            <div className="bento-card kpi-card kpi-card-wide">
                <div className="kpi-label">Cumulative Spent</div>
                <div className="kpi-value amber">${(data.stats.total_spent ?? 0).toFixed(4)}</div>
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
                <div className="kpi-label">Requests Blocked</div>
                <div className="kpi-value amber">{data.stats.requests_blocked ?? 0}</div>
            </div>
            <div className="bento-card kpi-card">
                <div className="kpi-label">Overspend Prevented</div>
                <div className="kpi-value">${(data.stats.overspend_prevented ?? 0).toFixed(4)}</div>
            </div>
            <div className="bento-card kpi-card">
                <div className="kpi-label">Active Agents</div>
                <div className="kpi-value">{activeAgents} / {totalAgents}</div>
            </div>
        </div>

        <div className="section-label mint">{"// 02 — Live audit feed"}</div>

        <div className="bento-grid">
            <div className="bento-card col-12">
                <div className="panel-header">
                    <h2>Live Audit Feed</h2>
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
                          </div>
                        </div>
                      ))
                    )}
                </div>
            </div>
        </div>

        <div className="section-label">{"// 03 — Real-time telemetry"}</div>

        <div className="bento-grid">
            <div className="bento-card col-8">
                <div className="panel-header">
                    <h2>Fiscal Consumption Timeline</h2>
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

        {/* 05 — Mandate Synchronization */}
        <div className="section-label mint">{"// 05 — Mandate Synchronization"}</div>
        <div className="bento-grid" style={{marginBottom: '1.5rem'}}>
          <div className="bento-card col-12">
            <div className="panel-header">
              <h2>Control Plane Sync Status</h2>
            </div>
            <div style={{display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:'1.5rem', padding:'0.5rem 0'}}>
              {/* policy_version */}
              <div style={{display:'flex', flexDirection:'column', gap:'0.4rem'}}>
                <span style={{fontFamily:'var(--font-mono)', fontSize:'10px', color:'var(--text-tertiary)', textTransform:'uppercase', letterSpacing:'0.08em'}}>mandate_revision</span>
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
              {/* control_plane_healthy */}
              <div style={{display:'flex', flexDirection:'column', gap:'0.4rem'}}>
                <span style={{fontFamily:'var(--font-mono)', fontSize:'10px', color:'var(--text-tertiary)', textTransform:'uppercase', letterSpacing:'0.08em'}}>control_plane_healthy</span>
                <div style={{display:'flex', alignItems:'center', gap:'0.5rem', marginTop:'0.2rem'}}>
                  <div style={{
                    width:'10px', height:'10px', borderRadius:'50%',
                    background: data.policy_sync?.control_plane_healthy ? '#10B981' : '#EF4444',
                    boxShadow: data.policy_sync?.control_plane_healthy ? '0 0 8px #10B981' : '0 0 8px #EF4444',
                    flexShrink: 0,
                  }} />
                  <span style={{fontFamily:'var(--font-mono)', fontSize:'13px', fontWeight:600,
                    color: data.policy_sync?.control_plane_healthy ? 'var(--mint)' : '#EF4444'}}>
                    {data.policy_sync?.control_plane_healthy ? 'true' : 'false'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="section-label">{"// 04 — Agent ledger & administration"}</div>

        <div className="bento-grid">
            <div className="bento-card col-8">
                <div className="panel-header">
                    <h2>Agent Ledger</h2>
                </div>
                <div className="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Agent</th>
                                <th>Status</th>
                                <th>Budget</th>
                                <th>Spent</th>
                                <th>Remaining</th>
                                <th>Mandate Revision</th>
                                <th>Last Synced</th>
                                {data.has_expiry && <th>Expiry</th>}
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.mandates.length === 0 ? (
                              <tr><td colSpan={data.has_expiry ? 9 : 8} style={{textAlign:'center', color:'var(--text-tertiary)', fontFamily:'var(--font-mono)', fontSize:'12px'}}>{"// Mandate ledger empty"}</td></tr>
                            ) : (
                              data.mandates.map((m, i: number) => {
                                let badgeClass = 'badge-active';
                                if (m.status === 'exhausted') badgeClass = 'badge-exhausted';
                                if (m.status === 'expired') badgeClass = 'badge-expired';
                                const remaining = typeof m.remaining_headroom === 'number'
                                    ? m.remaining_headroom
                                    : ((m.budget_usd || 0) - (m.spent_usd || 0));

                                return (
                                  <tr key={i}>
                                      <td className="td-id">{m.id}</td>
                                      <td><span className={`badge ${badgeClass}`}>{m.status}</span></td>
                                      <td>${m.budget_usd.toFixed(4)}</td>
                                      <td>${m.spent_usd.toFixed(4)}</td>
                                      <td>${remaining.toFixed(4)}</td>
                                      <td>
                                          <span className="badge" style={{background: 'rgba(255,255,255,0.05)', color: '#8a8a8a'}}>
                                              v{m.policy_version || data.policy_sync?.policy_version || '—'}
                                          </span>
                                      </td>
                                      <td style={{color:'var(--text-secondary)', fontFamily:'var(--font-mono)', fontSize:'11px'}}>
                                          {data.policy_sync?.last_synced_at ? new Date(data.policy_sync.last_synced_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'}) : '—'}
                                      </td>
                                      {data.has_expiry && (
                                        <td style={{color:'var(--text-secondary)', fontFamily:'var(--font-mono)', fontSize:'11px'}}>
                                          {formatExpiry(m.expires_at) ?? '—'}
                                        </td>
                                      )}
                                      <td>
                                          <button className="btn btn-danger" onClick={() => revokeMandate(m.id)}>Revoke</button>
                                          <button className="btn" onClick={() => {
                                            setFormState({ id: m.id, budget: m.budget_usd.toString(), expiry: '' });
                                          }}>Top-up</button>
                                      </td>
                                  </tr>
                                )
                              })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
            <div className="bento-card col-4">
                <div className="panel-header">
                    <h2>Issue Mandate</h2>
                </div>
                <form onSubmit={handleUpsert} style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="form-mandate-id">Agent ID</label>
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
                    <button type="submit" className="btn-submit">Apply Mandate</button>
                    <div className={`feedback-message ${feedback.type}`}>{feedback.text}</div>
                </form>

                <div className="panel-header" style={{ marginTop: '2rem' }}>
                    <h2>Push Policy Revision</h2>
                </div>
                <form onSubmit={handlePushPolicy} style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="policy-agent-id">Agent ID</label>
                        <input type="text" id="policy-agent-id" required placeholder="e.g. customer_support_agent" className="form-input" value={policyForm.agentId} onChange={e => setPolicyForm({...policyForm, agentId: e.target.value})} />
                    </div>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="policy-json">Policy JSON (Rego Bundle)</label>
                        <textarea id="policy-json" required rows={5} placeholder='{"max_usd": 150.0}' className="form-input" style={{fontFamily: 'var(--font-mono)', fontSize: '11px', resize: 'vertical'}} value={policyForm.policyJson} onChange={e => setPolicyForm({...policyForm, policyJson: e.target.value})} />
                    </div>
                    <button type="submit" className="btn-submit" style={{background: 'var(--blue)'}}>Sign & Push vNext</button>
                    <div className={`feedback-message ${policyFeedback.type}`}>{policyFeedback.text}</div>
                </form>
            </div>
        </div>
      </div>
    </>
  );
}
