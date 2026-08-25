"use client";

import React, { useMemo, useState } from 'react';
import { money } from '@/lib/format';

interface Share {
  agentId: string;
  amount: string;
}

interface Props {
  knownAgents: string[];
  onSaved: () => void;
}

/**
 * Bulk and structural tooling. Deliberately collapsed: a tenant who only wants
 * "cap my agents" never has to read any of it.
 */
export default function AdvancedTools({ knownAgents, onSaved }: Props) {
  const [fleetId, setFleetId] = useState('');
  const [fleetTotal, setFleetTotal] = useState('');
  const [shares, setShares] = useState<Share[]>([{ agentId: '', amount: '' }]);
  const [fleetFeedback, setFleetFeedback] = useState({ text: '', type: '' });

  const [orgJson, setOrgJson] = useState('');
  const [orgFleetId, setOrgFleetId] = useState('');
  const [orgFeedback, setOrgFeedback] = useState({ text: '', type: '' });

  const [aliases, setAliases] = useState('');
  const [aliasFeedback, setAliasFeedback] = useState({ text: '', type: '' });

  const allocated = useMemo(
    () => shares.reduce((sum, s) => sum + (parseFloat(s.amount) || 0), 0),
    [shares]
  );
  const total = parseFloat(fleetTotal) || 0;
  const unallocated = total - allocated;
  const oversubscribed = total > 0 && allocated > total + 1e-9;

  const updateShare = (index: number, patch: Partial<Share>) => {
    setShares((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  };

  const splitEvenly = () => {
    const named = shares.filter((s) => s.agentId.trim());
    if (named.length === 0 || total <= 0) return;
    const each = Math.floor((total / named.length) * 100) / 100;
    let cursor = 0;
    setShares((prev) => prev.map((s) => {
      if (!s.agentId.trim()) return s;
      cursor += 1;
      // Last agent absorbs the rounding remainder so the split always sums to the total.
      const amount = cursor === named.length
        ? Math.round((total - each * (named.length - 1)) * 100) / 100
        : each;
      return { ...s, amount: String(amount) };
    }));
  };

  const submitFleet = async (e: React.FormEvent) => {
    e.preventDefault();
    const partitions: Record<string, number> = {};
    for (const share of shares) {
      const id = share.agentId.trim();
      const amount = parseFloat(share.amount);
      if (!id || !Number.isFinite(amount)) continue;
      partitions[id] = amount;
    }
    if (Object.keys(partitions).length === 0) {
      setFleetFeedback({ text: 'Add at least one agent and amount.', type: 'error' });
      return;
    }

    try {
      const res = await fetch('/api/fleets/partition', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fleet_id: fleetId, total_usd: total, partitions }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Could not split this fleet');
      setFleetFeedback({
        text: `Published budgets for ${json.agents?.length ?? 0} agents in ${json.fleet_id}.`,
        type: 'success',
      });
      onSaved();
    } catch (err) {
      setFleetFeedback({ text: err instanceof Error ? err.message : String(err), type: 'error' });
    }
  };

  const submitOrg = async (e: React.FormEvent) => {
    e.preventDefault();
    let org: unknown;
    try {
      org = JSON.parse(orgJson);
    } catch {
      setOrgFeedback({ text: 'That is not valid JSON.', type: 'error' });
      return;
    }
    try {
      const res = await fetch('/api/orgs/compile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          org,
          fleet_id: orgFleetId || undefined,
          push: Boolean(orgFleetId.trim()),
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Could not compile this structure');
      const caps = Object.entries(json.agent_caps || {})
        .map(([k, v]) => `${k} ${money(Number(v))}`)
        .join(', ');
      setOrgFeedback({
        text: `${Object.keys(json.agent_caps || {}).length} agent budgets calculated: ${caps}` +
          (json.fleet ? ' — published.' : ' — not published (add a fleet name to publish).'),
        type: 'success',
      });
      onSaved();
    } catch (err) {
      setOrgFeedback({ text: err instanceof Error ? err.message : String(err), type: 'error' });
    }
  };

  const submitAliases = async (e: React.FormEvent) => {
    e.preventDefault();
    const parsed = aliases
      .split(/[\n,]/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((alias) => ({ alias }));

    if (parsed.length === 0) {
      setAliasFeedback({ text: 'Enter at least one environment variable name.', type: 'error' });
      return;
    }

    try {
      const res = await fetch('/api/secrets/aliases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ aliases: parsed }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Those names are not usable');
      setAliasFeedback({
        text: `${(json.aliases || []).length} name(s) look right. Nothing was stored — the values never leave your host.`,
        type: 'success',
      });
    } catch (err) {
      setAliasFeedback({ text: err instanceof Error ? err.message : String(err), type: 'error' });
    }
  };

  return (
    <details className="bento-card col-12 disclosure disclosure-panel">
      <summary>
        <span className="disclosure-title">More ways to set budgets</span>
        <span className="panel-note">Split a shared pot · mirror your org chart · check key names</span>
      </summary>

      <div className="advanced-grid">
        <section className="advanced-section">
          <h3>Split a shared pot</h3>
          <p className="panel-help">
            Divide one total across several agents. Each gets its own hard ceiling, so one
            agent can never eat another&apos;s share.
          </p>
          <form onSubmit={submitFleet} className="stack">
            <div className="field">
              <label htmlFor="fleet-name">Name this group</label>
              <input
                id="fleet-name"
                type="text"
                required
                className="form-input"
                placeholder="production"
                value={fleetId}
                onChange={(e) => setFleetId(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="fleet-total">Total to share</label>
              <div className="budget-amount">
                <span aria-hidden="true">$</span>
                <input
                  id="fleet-total"
                  type="number"
                  required
                  step="0.01"
                  min="0.01"
                  className="form-input"
                  placeholder="1000.00"
                  value={fleetTotal}
                  onChange={(e) => setFleetTotal(e.target.value)}
                />
              </div>
            </div>

            {shares.map((share, index) => (
              <div key={index} className="share-row">
                <input
                  type="text"
                  className="form-input"
                  aria-label={`Agent ${index + 1}`}
                  list="known-agents"
                  placeholder="agent name"
                  value={share.agentId}
                  onChange={(e) => updateShare(index, { agentId: e.target.value })}
                />
                <div className="budget-amount">
                  <span aria-hidden="true">$</span>
                  <input
                    type="number"
                    className="form-input"
                    aria-label={`Share for agent ${index + 1}`}
                    step="0.01"
                    min="0.01"
                    placeholder="0.00"
                    value={share.amount}
                    onChange={(e) => updateShare(index, { amount: e.target.value })}
                  />
                </div>
                <button
                  type="button"
                  className="btn btn-inline"
                  aria-label={`Remove agent ${index + 1}`}
                  onClick={() => setShares((prev) => prev.filter((_, i) => i !== index))}
                >
                  Remove
                </button>
              </div>
            ))}
            <datalist id="known-agents">
              {knownAgents.map((a) => <option key={a} value={a} />)}
            </datalist>

            <div className="inline-actions">
              <button type="button" className="btn" onClick={() => setShares((p) => [...p, { agentId: '', amount: '' }])}>
                Add agent
              </button>
              <button type="button" className="btn" onClick={splitEvenly} disabled={total <= 0}>
                Split evenly
              </button>
            </div>

            {total > 0 ? (
              <p className={`allocation-note${oversubscribed ? ' is-error' : ''}`}>
                {oversubscribed
                  ? `Over by ${money(allocated - total)} — reduce a share before publishing.`
                  : `${money(unallocated)} of ${money(total)} still unallocated.`}
              </p>
            ) : null}

            <button type="submit" className="btn-submit" disabled={oversubscribed}>Publish budgets</button>
            <div className={`feedback-message ${fleetFeedback.type}`} role="status">{fleetFeedback.text}</div>
          </form>
        </section>

        <section className="advanced-section">
          <h3>Mirror your org chart</h3>
          <p className="panel-help">
            Describe company → department → agent once and let Mintry work out each agent&apos;s
            ceiling. A child with no budget of its own splits what its parent has left.
          </p>
          <form onSubmit={submitOrg} className="stack">
            <div className="field">
              <label htmlFor="org-json">Structure</label>
              <textarea
                id="org-json"
                required
                rows={8}
                className="form-input mono"
                placeholder={'{\n  "id": "acme",\n  "kind": "company",\n  "budget_usd": 1000,\n  "children": [\n    { "id": "support_bot", "kind": "agent", "budget_usd": 600 },\n    { "id": "research_bot", "kind": "agent" }\n  ]\n}'}
                value={orgJson}
                onChange={(e) => setOrgJson(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="org-fleet">Publish as group (optional)</label>
              <input
                id="org-fleet"
                type="text"
                className="form-input"
                placeholder="leave empty to preview only"
                value={orgFleetId}
                onChange={(e) => setOrgFleetId(e.target.value)}
              />
            </div>
            <button type="submit" className="btn-submit">
              {orgFleetId.trim() ? 'Calculate and publish' : 'Calculate only'}
            </button>
            <div className={`feedback-message ${orgFeedback.type}`} role="status">{orgFeedback.text}</div>
          </form>
        </section>

        <section className="advanced-section">
          <h3>Check your key names</h3>
          <p className="panel-help">
            Mintry never stores provider API keys. Paste the environment variable
            <em> names</em> your agents read so we can confirm they are valid references.
          </p>
          <form onSubmit={submitAliases} className="stack">
            <div className="field">
              <label htmlFor="alias-names">Variable names</label>
              <textarea
                id="alias-names"
                rows={4}
                className="form-input mono"
                placeholder={'OPENAI_API_KEY\nANTHROPIC_API_KEY'}
                value={aliases}
                onChange={(e) => setAliases(e.target.value)}
              />
            </div>
            <button type="submit" className="btn-submit">Check names</button>
            <div className={`feedback-message ${aliasFeedback.type}`} role="status">{aliasFeedback.text}</div>
          </form>
        </section>
      </div>
    </details>
  );
}
