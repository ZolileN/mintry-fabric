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

interface Mandate { id: string; status: string; budget_usd: number; spent_usd: number; expires_at: string | null; remaining_headroom?: number; }
interface LogEvent { action: string; timestamp: string; mandate_id: string; details?: string; amount?: number; }
interface TopMandate { id: string; spent_usd: number; }
interface DashboardData {
  stats: { total_budget: number; total_spent: number; remaining_headroom: number };
  mandates: Mandate[];
  top_mandates: TopMandate[];
  history: LogEvent[];
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData>({
    stats: { total_budget: 0, total_spent: 0, remaining_headroom: 0 },
    mandates: [],
    top_mandates: [],
    history: []
  });

  const [formState, setFormState] = useState({ id: '', budget: '', expiry: '' });
  const [feedback, setFeedback] = useState({ text: '', type: '' });

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

  const activeCount = data.mandates.filter((m) => m.status === 'active').length;

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
            showFeedback("Mandate allocated successfully", "success");
            setFormState({ id: '', budget: '', expiry: '' });
            fetchSummary();
        } else {
            showFeedback(json.error || "Allocation failed", "error");
        }
    } catch {
        showFeedback("Connection error", "error");
    }
  };

  const revokeMandate = async (id: string) => {
    if (!confirm(`Are you sure you want to revoke budget for mandate: ${id}?`)) return;
    try {
        const res = await fetch('/api/mandates/revoke', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        const json = await res.json();
        if (json.success) {
            showFeedback(`Mandate ${id} revoked`, "success");
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

  // Prepare chart data
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
        borderColor: '#0f8',
        backgroundColor: 'rgba(0, 255, 136, 0.03)',
        borderWidth: 2,
        fill: true,
        tension: 0.2,
        pointBackgroundColor: '#0f8',
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
        
        <div className="section-label mint">{"// 01 — Executive fiscal indicators"}</div>

        <div className="kpi-grid">
            <div className="bento-card kpi-card">
                <div className="kpi-label">Allocated Budget</div>
                <div className="kpi-value">${data.stats.total_budget.toFixed(4)}</div>
            </div>
            <div className="bento-card kpi-card">
                <div className="kpi-label">Cumulative Spend</div>
                <div className="kpi-value mint">${data.stats.total_spent.toFixed(4)}</div>
            </div>
            <div className="bento-card kpi-card">
                <div className="kpi-label">Remaining Headroom</div>
                <div className="kpi-value blue">${data.stats.remaining_headroom.toFixed(4)}</div>
            </div>
            <div className="bento-card kpi-card">
                <div className="kpi-label">Active Mandates</div>
                <div className="kpi-value">{activeCount}</div>
            </div>
        </div>

        <div className="section-label">{"// 02 — Real-time telemetry"}</div>

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

        <div className="section-label">{"// 03 — System ledger & administration"}</div>

        <div className="bento-grid">
            <div className="bento-card col-8">
                <div className="panel-header">
                    <h2>Mandates Ledger</h2>
                </div>
                <div className="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Mandate ID</th>
                                <th>Status</th>
                                <th>Budget</th>
                                <th>Spent</th>
                                <th>Remaining</th>
                                <th>Expiry</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.mandates.length === 0 ? (
                              <tr><td colSpan={7} style={{textAlign:'center', color:'var(--text-tertiary)', fontFamily:'var(--font-mono)', fontSize:'12px'}}>{"// Database ledger empty"}</td></tr>
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
                                      <td style={{color:'var(--text-secondary)', fontFamily:'var(--font-mono)', fontSize:'11px'}}>{m.expires_at}</td>
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
                    <h2>Allocate / Update Mandate</h2>
                </div>
                <form onSubmit={handleUpsert} style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                    <div style={{display: 'flex', flexDirection: 'column', gap: '0.3rem'}}>
                        <label className="kpi-label" htmlFor="form-mandate-id">Mandate ID</label>
                        <input type="text" id="form-mandate-id" required placeholder="e.g. nightly_summarizer" className="form-input" value={formState.id} onChange={e => setFormState({...formState, id: e.target.value})} />
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
            </div>
        </div>

        <div className="section-label">{"// 04 — Security audit logs"}</div>

        <div className="bento-grid">
            <div className="bento-card col-12">
                <div className="panel-header">
                    <h2>Live Audit Feed</h2>
                </div>
                <div className="event-list" style={{maxHeight: '350px'}}>
                    {data.history.length === 0 ? (
                      <p style={{color:'var(--text-tertiary)', fontFamily:'var(--font-mono)', textAlign:'center', paddingTop:'4rem', fontSize:'12px'}}>{"// Logs empty"}</p>
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
      </div>
    </>
  );
}
