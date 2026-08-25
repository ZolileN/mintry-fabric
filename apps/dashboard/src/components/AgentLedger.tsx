"use client";

import React, { useMemo, useState } from 'react';
import type { Mandate, PolicySync } from '@/lib/dashboard-types';
import { money, percent } from '@/lib/format';

interface Props {
  mandates: Mandate[];
  policySync?: PolicySync;
  hasExpiry?: boolean;
  localGovernance: boolean;
  onAdjust: (mandateId: string) => void;
  onPause: (mandateId: string) => void;
}

function healthOf(mandate: Mandate): { label: string; tone: string } {
  const budget = mandate.budget_usd || 0;
  const spent = mandate.spent_usd || 0;
  const utilization = budget > 0 ? spent / budget : 0;

  if (mandate.status === 'exhausted') return { label: 'Blocked — out of budget', tone: 'critical' };
  if (mandate.status === 'expired') return { label: 'Blocked — expired', tone: 'critical' };
  if (utilization >= 0.95) return { label: 'Almost out', tone: 'critical' };
  if (utilization >= 0.8) return { label: 'Getting close', tone: 'warning' };
  if (budget > 0 && spent === 0) return { label: 'Idle', tone: 'idle' };
  return { label: 'Healthy', tone: 'ok' };
}

export default function AgentLedger({
  mandates,
  policySync,
  hasExpiry,
  localGovernance,
  onAdjust,
  onPause,
}: Props) {
  const [query, setQuery] = useState('');

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = needle
      ? mandates.filter((m) => m.id.toLowerCase().includes(needle))
      : mandates;
    // Worst first: an operator scanning this table cares about trouble, not the alphabet.
    return [...rows].sort((a, b) => {
      const ua = a.budget_usd > 0 ? a.spent_usd / a.budget_usd : 0;
      const ub = b.budget_usd > 0 ? b.spent_usd / b.budget_usd : 0;
      return ub - ua;
    });
  }, [mandates, query]);

  return (
    <div className="bento-card col-12">
      <div className="panel-header">
        <h2>Agents</h2>
        <span className="panel-note">
          {mandates.length} total
          {policySync?.policy_version != null ? ` · policy v${policySync.policy_version}` : ''}
        </span>
      </div>

      <label className="visually-hidden" htmlFor="agent-search">Filter agents by name</label>
      <input
        id="agent-search"
        type="search"
        className="form-input search-input"
        placeholder="Filter agents by name…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th scope="col">Agent</th>
              <th scope="col">Health</th>
              <th scope="col">Used</th>
              <th scope="col">Ceiling</th>
              <th scope="col">Left</th>
              {hasExpiry ? <th scope="col">Expires</th> : null}
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={hasExpiry ? 7 : 6} className="empty-cell">
                  {mandates.length === 0
                    ? 'No agents reporting yet. They appear here on their first request.'
                    : `No agent matches “${query}”.`}
                </td>
              </tr>
            ) : (
              visible.map((mandate) => {
                const budget = mandate.budget_usd || 0;
                const spent = mandate.spent_usd || 0;
                const remaining = typeof mandate.remaining_headroom === 'number'
                  ? mandate.remaining_headroom
                  : budget - spent;
                const utilization = budget > 0 ? spent / budget : 0;
                const health = healthOf(mandate);

                return (
                  <tr key={mandate.id}>
                    <td className="td-id">{mandate.id}</td>
                    <td>
                      <span className={`chip chip-${health.tone}`}>{health.label}</span>
                    </td>
                    <td>
                      <div className="usage-cell">
                        <span className="usage-figure">
                          {money(spent)} <span className="usage-pct">({percent(utilization)})</span>
                        </span>
                        <div className="progress-bar-container">
                          <div
                            className={`progress-bar-fill tone-${health.tone}`}
                            style={{ width: `${Math.min(utilization * 100, 100)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="td-money">{money(budget)}</td>
                    <td className="td-money">{money(remaining)}</td>
                    {hasExpiry ? (
                      <td className="td-muted">
                        {mandate.expires_at ? new Date(mandate.expires_at).toLocaleDateString() : '—'}
                      </td>
                    ) : null}
                    <td className="td-actions">
                      <button
                        type="button"
                        className="btn btn-inline"
                        onClick={() => onAdjust(mandate.id)}
                      >
                        Adjust budget
                      </button>
                      {localGovernance ? (
                        <button
                          type="button"
                          className="btn btn-inline btn-danger"
                          onClick={() => onPause(mandate.id)}
                        >
                          Stop spend
                        </button>
                      ) : null}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
