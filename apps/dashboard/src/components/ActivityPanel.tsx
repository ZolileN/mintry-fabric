"use client";

import React, { useMemo, useState } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import type { LogEvent } from '@/lib/dashboard-types';
import { money, shortTime } from '@/lib/format';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

/** Plain-language names for audit actions, so the feed reads without a glossary. */
const ACTION_COPY: Record<string, string> = {
  allow: 'Allowed',
  block: 'Blocked',
  spend: 'Charged',
  create: 'Budget created',
  top_up: 'Budget changed',
  exhaust: 'Budget stopped',
  expire: 'Expired',
  notice: 'Alert sent',
  auto_enroll: 'New agent enrolled',
};

const FILTERS: { key: string; label: string; actions: string[] | null }[] = [
  { key: 'all', label: 'Everything', actions: null },
  { key: 'blocked', label: 'Blocked', actions: ['block', 'exhaust', 'expire'] },
  { key: 'alerts', label: 'Alerts', actions: ['notice', 'auto_enroll'] },
  { key: 'charges', label: 'Charges', actions: ['spend'] },
];

interface Props {
  history: LogEvent[];
}

export default function ActivityPanel({ history }: Props) {
  const [filter, setFilter] = useState('all');

  const chart = useMemo(() => {
    let running = 0;
    const labels: string[] = [];
    const points: number[] = [];
    for (const log of [...history].reverse()) {
      if (log.action !== 'spend') continue;
      running += log.amount || 0;
      labels.push(shortTime(log.timestamp));
      points.push(Number(running.toFixed(4)));
    }
    return { labels: labels.slice(-30), points: points.slice(-30) };
  }, [history]);

  const filtered = useMemo(() => {
    const active = FILTERS.find((f) => f.key === filter);
    if (!active?.actions) return history;
    return history.filter((h) => active.actions!.includes(h.action));
  }, [history, filter]);

  return (
    <>
      <div className="bento-card col-7">
        <div className="panel-header">
          <h2>Spend over time</h2>
          <span className="panel-note">Cumulative, most recent {chart.points.length} charges</span>
        </div>
        <div className="chart-container">
          {chart.points.length > 0 ? (
            <Line
              data={{
                labels: chart.labels,
                datasets: [{
                  label: 'Cumulative spend',
                  data: chart.points,
                  borderColor: '#10B981',
                  backgroundColor: 'rgba(16, 185, 129, 0.06)',
                  borderWidth: 2,
                  fill: true,
                  tension: 0.25,
                  pointRadius: 0,
                  pointHoverRadius: 4,
                }],
              }}
              options={{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  legend: { display: false },
                  tooltip: {
                    callbacks: {
                      label: (ctx: { parsed: { y: number } }) => money(ctx.parsed.y),
                    },
                  },
                },
                scales: {
                  x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: { color: '#9a9a9a', font: { size: 10 }, maxTicksLimit: 8 },
                  },
                  y: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: {
                      color: '#9a9a9a',
                      font: { size: 10 },
                      callback: (value: string | number) => money(Number(value)),
                    },
                  },
                },
              } as unknown as object}
            />
          ) : (
            <p className="empty-note">No charges recorded yet.</p>
          )}
        </div>
      </div>

      <div className="bento-card col-5">
        <div className="panel-header">
          <h2>Activity</h2>
        </div>
        <div className="filter-chips" role="group" aria-label="Filter activity">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              className={`filter-chip${filter === f.key ? ' is-active' : ''}`}
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="event-list">
          {filtered.length === 0 ? (
            <p className="empty-note">Nothing here yet.</p>
          ) : (
            filtered.slice(0, 60).map((log, i) => (
              <div key={`${log.timestamp}-${i}`} className="event-item">
                <div className="event-header">
                  <span className={`event-action ${log.action}`}>
                    {ACTION_COPY[log.action] ?? log.action.replace('_', ' ')}
                  </span>
                  <span className="event-time">{shortTime(log.timestamp)}</span>
                </div>
                <div className="event-body">
                  <code>{log.mandate_id}</code>
                  {log.details ? ` — ${log.details}` : ''}
                  {typeof log.amount === 'number' && log.amount !== 0 && log.action === 'spend'
                    ? ` (${money(log.amount)})`
                    : ''}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
}
