"use client";

import React from 'react';
import type { Attention, AttentionItem, BudgetNotice } from '@/lib/dashboard-types';
import { money, relativeFuture, relativeTime } from '@/lib/format';

const SEVERITY_LABEL: Record<string, string> = {
  critical: 'Needs action',
  warning: 'Worth a look',
  info: 'Suggestion',
};

const ACTION_LABEL: Record<string, string> = {
  raise_budget: 'Raise budget',
  extend_expiry: 'Extend expiry',
  reclaim_budget: 'Reduce budget',
  check_control_plane: 'Check connection',
};

interface Props {
  attention?: Attention;
  notices: BudgetNotice[];
  loading: boolean;
  error: string | null;
  lastUpdated: number | null;
  now: number;
  onFix: (item: AttentionItem) => void;
}

export default function StatusHero({
  attention,
  notices,
  loading,
  error,
  lastUpdated,
  now,
  onFix,
}: Props) {
  if (error) {
    return (
      <section className="hero hero-error" aria-live="polite">
        <p className="hero-eyebrow">Can&apos;t reach your ledger</p>
        <h1 className="hero-headline">{error}</h1>
        <p className="hero-subhead">
          Your agents are unaffected — they enforce the last policy they verified locally,
          with or without this dashboard.
        </p>
      </section>
    );
  }

  if (loading || !attention) {
    return (
      <section className="hero hero-loading" aria-busy="true">
        <p className="hero-eyebrow">Checking your agents</p>
        <h1 className="hero-headline skeleton-text" aria-hidden="true" />
        <p className="hero-subhead skeleton-text short" aria-hidden="true" />
      </section>
    );
  }

  const items = attention.items ?? [];
  const latestNotice = notices[0];

  return (
    <section className={`hero hero-${attention.status}`} aria-live="polite">
      <p className="hero-eyebrow">
        <span className="hero-dot" aria-hidden="true" />
        {attention.status === 'ok' ? 'All clear' : 'Status'}
        {lastUpdated ? (
          <span className="hero-timestamp">
            {' '}· checked {relativeTime(new Date(lastUpdated).toISOString(), now)}
          </span>
        ) : null}
      </p>

      <h1 className="hero-headline">{attention.headline}</h1>
      <p className="hero-subhead">{attention.subhead}</p>

      {items.length > 0 ? (
        <ul className="attention-list">
          {items.map((item, i) => (
            <li key={`${item.mandate_id ?? 'platform'}-${i}`} className={`attention-item sev-${item.severity}`}>
              <div className="attention-copy">
                <span className={`attention-tag sev-${item.severity}`}>
                  {SEVERITY_LABEL[item.severity] ?? item.severity}
                </span>
                <p className="attention-headline">{item.headline}</p>
                <p className="attention-detail">{item.detail}</p>
              </div>
              {item.mandate_id && item.suggested_action && item.suggested_action !== 'check_control_plane' ? (
                <button type="button" className="btn btn-inline" onClick={() => onFix(item)}>
                  {ACTION_LABEL[item.suggested_action] ?? 'Adjust'}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="hero-reassurance">
          You don&apos;t need to check in. Mintry alerts your webhook when an agent crosses
          50%, 80% and 95% of its budget, and blocks spend at the cap either way.
        </p>
      )}

      {latestNotice ? (
        <p className="hero-footnote">
          Last alert sent {relativeTime(latestNotice.timestamp, now)}: {latestNotice.mandate_id} at{' '}
          {Math.round(latestNotice.threshold * 100)}% of {money(latestNotice.budget_usd)}
          {latestNotice.projected_exhaustion_at
            ? ` · projected to run out ${relativeFuture(latestNotice.projected_exhaustion_at, now)}`
            : ''}
          .
        </p>
      ) : null}
    </section>
  );
}
