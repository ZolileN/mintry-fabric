import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { SyncStore } from './store';

dotenv.config();

const app = express();
const port = process.env.PORT || 8080;
const store = new SyncStore();

app.use(cors());
app.use(express.json());

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'mintry-sync-api' });
});

app.get('/api/summary', (req, res) => {
  res.json(store.getSummary());
});

app.post('/api/mandates/upsert', (req, res) => {
  const { id, budget_usd, expires_at } = req.body as {
    id?: string;
    budget_usd?: number;
    expires_at?: string | null;
  };

  if (!id || budget_usd === undefined || Number.isNaN(Number(budget_usd))) {
    return res.status(400).json({ error: "Missing 'id' or 'budget_usd'" });
  }

  store.upsertMandate(id, Number(budget_usd), expires_at ?? null);
  return res.json({ success: true });
});

app.post('/api/mandates/revoke', (req, res) => {
  const { id } = req.body as { id?: string };

  if (!id) {
    return res.status(400).json({ error: "Missing mandate 'id'" });
  }

  store.revokeMandate(id);
  return res.json({ success: true });
});

// Endpoint for receiving WAL syncs from Enforcement Planes
app.post('/api/v1/sync', (req, res) => {
  const { mandate_id, spend, tokens } = req.body;
  
  if (!mandate_id) {
    return res.status(400).json({ error: 'mandate_id is required' });
  }

  const mandate = store.recordSync({
    mandateId: mandate_id,
    spend: spend !== undefined ? Number(spend) : undefined,
    tokens: tokens !== undefined ? Number(tokens) : undefined,
  });

  console.log(`Received sync for mandate ${mandate_id}: $${spend} (${tokens} tokens)`);
  res.json({ status: 'synced', mandate_id, mandate });
});

app.listen(port, () => {
  console.log(`Mintry Sync API (Control Plane) running on port ${port}`);
});
