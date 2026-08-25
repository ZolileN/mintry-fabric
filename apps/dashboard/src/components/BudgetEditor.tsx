"use client";

import React, { useEffect, useMemo, useState } from 'react';
import type { Governance, Mandate } from '@/lib/dashboard-types';
import { money } from '@/lib/format';

/** Reserved rule key: the cap applied to any agent nobody has budgeted yet. */
const DEFAULT_KEY = '__default__';

interface Edit {
  budget?: string;
  allow?: boolean;
}

interface NewRow {
  key: string;
  id: string;
  budget: string;
}

export interface EditableRow {
  id: string;
  budget: string;
  allow: boolean;
  spent: number;
  saved: number;
  changed: boolean;
}

interface Props {
  mandates: Mandate[];
  governance?: Governance;
  focusMandateId: string | null;
  onSaved: () => void;
}

export default function BudgetEditor({ mandates, governance, focusMandateId, onSaved }: Props) {
  // Edits are stored as overlays on top of server state rather than a copy of it,
  // so the 5-second poll refreshes untouched rows without discarding in-progress work.
  const [edits, setEdits] = useState<Record<string, Edit>>({});
  const [newRows, setNewRows] = useState<NewRow[]>([]);
  const [defaultEdit, setDefaultEdit] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ text: string; type: string }>({ text: '', type: '' });

  const central = governance?.authoring_mode === 'central_sign_and_push'
    || Boolean(governance?.control_plane_configured && !governance?.local_governance);

  const savedDefault = useMemo(() => {
    const existing = mandates.find((m) => m.id === DEFAULT_KEY);
    return existing ? String(existing.budget_usd) : '';
  }, [mandates]);
  const defaultCap = defaultEdit ?? savedDefault;
  const defaultChanged = defaultEdit !== null && defaultEdit !== savedDefault;

  const rows: EditableRow[] = useMemo(() => {
    return mandates
      .filter((m) => m.id !== DEFAULT_KEY)
      .map((m) => {
        const edit = edits[m.id] ?? {};
        const saved = m.budget_usd ?? 0;
        const budget = edit.budget ?? String(saved);
        const savedAllow = m.status !== 'exhausted' && m.status !== 'expired';
        const allow = edit.allow ?? savedAllow;
        const parsed = parseFloat(budget);
        return {
          id: m.id,
          budget,
          allow,
          spent: m.spent_usd ?? 0,
          saved,
          changed: (Number.isFinite(parsed) && parsed !== saved) || allow !== savedAllow,
        };
      })
      .sort((a, b) => a.id.localeCompare(b.id));
  }, [mandates, edits]);

  const changedRows = rows.filter((r) => r.changed);
  const validNewRows = newRows.filter(
    (r) => r.id.trim().length > 0 && Number.isFinite(parseFloat(r.budget))
  );
  const pendingCount = changedRows.length + validNewRows.length + (defaultChanged ? 1 : 0);

  useEffect(() => {
    if (!focusMandateId) return;
    const input = document.getElementById(`budget-${focusMandateId}`);
    if (!input) return;
    input.scrollIntoView({ behavior: 'smooth', block: 'center' });
    (input as HTMLInputElement).focus();
    (input as HTMLInputElement).select();
  }, [focusMandateId]);

  const editRow = (id: string, patch: Edit) => {
    setEdits((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  };

  const discard = () => {
    setEdits({});
    setNewRows([]);
    setDefaultEdit(null);
    setFeedback({ text: '', type: '' });
  };

  const pendingMap = useMemo(() => {
    const map: Record<string, { max_usd: number; allow: boolean }> = {};
    for (const row of changedRows) {
      map[row.id] = { max_usd: parseFloat(row.budget), allow: row.allow };
    }
    for (const row of validNewRows) {
      map[row.id.trim()] = { max_usd: parseFloat(row.budget), allow: true };
    }
    const parsedDefault = parseFloat(defaultCap);
    if (Number.isFinite(parsedDefault) && parsedDefault > 0) {
      map[DEFAULT_KEY] = { max_usd: parsedDefault, allow: true };
    }
    return map;
  }, [changedRows, validNewRows, defaultCap]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pendingCount === 0) return;

    setSaving(true);
    setFeedback({ text: '', type: '' });

    const parsedDefault = parseFloat(defaultCap);
    const defaultRule = Number.isFinite(parsedDefault) && parsedDefault > 0
      ? { [DEFAULT_KEY]: { max_usd: parsedDefault, allow: true } }
      : {};

    const targets = [
      ...changedRows.map((r) => ({ id: r.id, max_usd: parseFloat(r.budget), allow: r.allow })),
      ...validNewRows.map((r) => ({ id: r.id.trim(), max_usd: parseFloat(r.budget), allow: true })),
    ];

    try {
      if (central) {
        // One signed, versioned bundle per agent — the same shape fleet
        // partitioning publishes, so history stays consistent however it was authored.
        const publishTo = targets.length > 0
          ? targets
          : rows.map((r) => ({ id: r.id, max_usd: parseFloat(r.budget), allow: r.allow }));

        const results = await Promise.all(publishTo.map(async (target) => {
          const res = await fetch('/api/policies/sign', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              agent_id: target.id,
              mandates: {
                ...defaultRule,
                [target.id]: { max_usd: target.max_usd, allow: target.allow },
              },
            }),
          });
          const json = await res.json();
          if (!res.ok) throw new Error(json.error || `Could not publish a budget for ${target.id}`);
          return `${target.id} v${json.version}`;
        }));

        setFeedback({
          text: `Published: ${results.join(', ')}. Your agents pick this up within 30 seconds.`,
          type: 'success',
        });
      } else {
        for (const target of targets) {
          const res = await fetch('/api/mandates/upsert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: target.id, budget_usd: target.max_usd }),
          });
          const json = await res.json();
          if (!json.success) throw new Error(json.error || `Could not save ${target.id}`);
        }
        if (defaultChanged && Number.isFinite(parsedDefault) && parsedDefault > 0) {
          const res = await fetch('/api/mandates/upsert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: DEFAULT_KEY, budget_usd: parsedDefault }),
          });
          const json = await res.json();
          if (!json.success) throw new Error(json.error || 'Could not save the default ceiling');
        }
        setFeedback({
          text: `Saved ${pendingCount} change${pendingCount === 1 ? '' : 's'}. Enforcement is already using them.`,
          type: 'success',
        });
      }

      setEdits({});
      setNewRows([]);
      setDefaultEdit(null);
      onSaved();
    } catch (err) {
      setFeedback({ text: err instanceof Error ? err.message : String(err), type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bento-card col-12">
      <div className="panel-header">
        <h2>Budgets</h2>
        <span className="panel-note">
          {central
            ? 'Saved as a signed, versioned policy'
            : 'Saved to this host\u2019s ledger'}
        </span>
      </div>

      <p className="panel-help">
        Set a dollar ceiling per agent. Mintry blocks spend at the ceiling and alerts you on
        the way there — you don&apos;t need to come back and check.
      </p>

      <form onSubmit={save}>
        <div className="budget-rows">
          <div className="budget-row budget-row-head" aria-hidden="true">
            <span>Agent</span>
            <span>Ceiling</span>
            <span>Allowed</span>
            <span />
          </div>

          {rows.length === 0 && newRows.length === 0 ? (
            <p className="empty-note">
              No agents yet. Add one below, or just call <code>mintry.init()</code> in your app —
              agents show up here on their first request.
            </p>
          ) : null}

          {rows.map((row) => (
            <div key={row.id} className={`budget-row${row.changed ? ' is-dirty' : ''}`}>
              <label className="budget-agent" htmlFor={`budget-${row.id}`}>
                <span className="budget-agent-id">{row.id}</span>
                <span className="budget-agent-spent">{money(row.spent)} spent</span>
              </label>

              <div className="budget-amount">
                <span aria-hidden="true">$</span>
                <input
                  type="number"
                  id={`budget-${row.id}`}
                  className="form-input"
                  aria-label={`Ceiling for ${row.id}`}
                  step="0.01"
                  min="0"
                  value={row.budget}
                  onChange={(e) => editRow(row.id, { budget: e.target.value })}
                />
              </div>

              <label className="budget-toggle">
                <input
                  type="checkbox"
                  checked={row.allow}
                  aria-label={`Allow requests from ${row.id}`}
                  onChange={(e) => editRow(row.id, { allow: e.target.checked })}
                />
                <span>{row.allow ? 'Yes' : 'Paused'}</span>
              </label>

              <span className="budget-row-status">
                {row.changed ? 'unsaved' : ''}
              </span>
            </div>
          ))}

          {newRows.map((row, index) => (
            <div key={row.key} className="budget-row is-dirty">
              <input
                type="text"
                className="form-input"
                aria-label={`Name for new agent ${index + 1}`}
                placeholder="agent name, e.g. support_bot"
                value={row.id}
                onChange={(e) => setNewRows((prev) =>
                  prev.map((r) => (r.key === row.key ? { ...r, id: e.target.value } : r)))}
              />
              <div className="budget-amount">
                <span aria-hidden="true">$</span>
                <input
                  type="number"
                  className="form-input"
                  aria-label={`Ceiling for new agent ${index + 1}`}
                  step="0.01"
                  min="0"
                  placeholder="0.00"
                  value={row.budget}
                  onChange={(e) => setNewRows((prev) =>
                    prev.map((r) => (r.key === row.key ? { ...r, budget: e.target.value } : r)))}
                />
              </div>
              <span className="budget-toggle-static">Yes</span>
              <button
                type="button"
                className="btn btn-inline"
                aria-label={`Remove new agent ${index + 1}`}
                onClick={() => setNewRows((prev) => prev.filter((r) => r.key !== row.key))}
              >
                Remove
              </button>
            </div>
          ))}

          <div className="budget-row budget-row-default">
            <label className="budget-agent" htmlFor="budget-default">
              <span className="budget-agent-id">Every new agent</span>
              <span className="budget-agent-spent">Applied automatically on its first request</span>
            </label>
            <div className="budget-amount">
              <span aria-hidden="true">$</span>
              <input
                type="number"
                id="budget-default"
                className="form-input"
                aria-label="Default ceiling for agents that have never been budgeted"
                step="0.01"
                min="0"
                placeholder="none"
                value={defaultCap}
                onChange={(e) => setDefaultEdit(e.target.value)}
              />
            </div>
            <span className="budget-toggle-static">Yes</span>
            <span className="budget-row-status">{defaultChanged ? 'unsaved' : ''}</span>
          </div>
        </div>

        <div className="budget-actions">
          <button
            type="button"
            className="btn"
            onClick={() => setNewRows((prev) => [
              ...prev,
              { key: `new-${Date.now()}-${prev.length}`, id: '', budget: '' },
            ])}
          >
            Add an agent
          </button>
          <div className="budget-actions-right">
            {pendingCount > 0 ? (
              <button type="button" className="btn" onClick={discard} disabled={saving}>Discard</button>
            ) : null}
            <button
              type="submit"
              className="btn-submit btn-inline-submit"
              disabled={saving || pendingCount === 0}
            >
              {saving
                ? 'Saving…'
                : pendingCount === 0
                  ? 'No changes to save'
                  : `Save ${pendingCount} change${pendingCount === 1 ? '' : 's'}`}
            </button>
          </div>
        </div>

        <div className={`feedback-message ${feedback.type}`} role="status">{feedback.text}</div>
      </form>

      <details className="disclosure">
        <summary>Review as JSON</summary>
        <p className="panel-help">
          Exactly what gets {central ? 'signed and published' : 'written to the ledger'}.
          Read-only — edit the rows above.
        </p>
        <pre className="json-preview">
          {pendingCount === 0 ? '// no pending changes' : JSON.stringify(pendingMap, null, 2)}
        </pre>
      </details>
    </div>
  );
}
