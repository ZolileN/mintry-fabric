import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';

dotenv.config();

const app = express();
const port = process.env.PORT || 8080;

app.use(cors());
app.use(express.json());

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'mintry-sync-api' });
});

// Endpoint for receiving WAL syncs from Enforcement Planes
app.post('/api/v1/sync', (req, res) => {
  const { mandate_id, spend, tokens } = req.body;
  
  if (!mandate_id) {
    return res.status(400).json({ error: 'mandate_id is required' });
  }

  // TODO: Insert into central Postgres Database
  console.log(`Received sync for mandate ${mandate_id}: $${spend} (${tokens} tokens)`);
  res.json({ status: 'synced', mandate_id });
});

app.listen(port, () => {
  console.log(`Mintry Sync API (Control Plane) running on port ${port}`);
});
