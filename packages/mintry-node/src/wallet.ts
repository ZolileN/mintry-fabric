import Database from 'better-sqlite3';
import fs from 'fs';
import path from 'path';

export interface MandateRow {
  id: string;
  budget_usd: number;
  spent_usd: number;
  status: string;
  expires_at: string | null;
}

export class MintryWallet {
  private db: Database.Database;

  constructor(dbPath: string) {
    // Expand ~
    if (dbPath.startsWith('~/')) {
      const homeDir = process.env.HOME || process.env.USERPROFILE || '';
      dbPath = path.join(homeDir, dbPath.slice(2));
    }

    const dir = path.dirname(dbPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
    this.db.pragma('synchronous = NORMAL');
    this._initSchema();
    
    // Seed default mandate if not exists
    if (this.getMandate('mt_task_882x').status === 'unknown') {
      this.createMandate('mt_task_882x', 1.0);
    }
  }

  private _initSchema() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS mandates (
          id TEXT PRIMARY KEY,
          budget_usd REAL NOT NULL,
          spent_usd REAL DEFAULT 0.0,
          status TEXT DEFAULT 'active',
          expires_at TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
      );
    `);

    this.db.exec(`
      CREATE TABLE IF NOT EXISTS mandate_audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          mandate_id TEXT NOT NULL,
          timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
          action TEXT NOT NULL,
          amount REAL DEFAULT 0.0,
          details TEXT
      );
    `);

    this.db.exec(`
      CREATE INDEX IF NOT EXISTS idx_mandates_status ON mandates(status);
      CREATE INDEX IF NOT EXISTS idx_audit_mandate ON mandate_audit_log(mandate_id);
    `);
  }

  private _logAudit(mandateId: string, action: string, amount: number, details: string) {
    const stmt = this.db.prepare(`
      INSERT INTO mandate_audit_log (mandate_id, action, amount, details, timestamp)
      VALUES (?, ?, ?, ?, ?)
    `);
    stmt.run(mandateId, action, amount, details, new Date().toISOString());
  }

  public getMandate(mandateId: string): MandateRow {
    const stmt = this.db.prepare('SELECT id, budget_usd, spent_usd, status, expires_at FROM mandates WHERE id = ?');
    const row = stmt.get(mandateId) as MandateRow | undefined;
    
    if (!row) {
      return {
        id: mandateId,
        budget_usd: 0.0,
        spent_usd: 0.0,
        status: 'unknown',
        expires_at: null
      };
    }
    return row;
  }

  public createMandate(mandateId: string, maxUsd: number, expiresAt: Date | null = null): void {
    const expiresAtStr = expiresAt ? expiresAt.toISOString() : null;
    const stmt = this.db.prepare(`
      INSERT INTO mandates (id, budget_usd, status, expires_at)
      VALUES (?, ?, 'active', ?)
    `);
    stmt.run(mandateId, maxUsd, expiresAtStr);
    this._logAudit(mandateId, 'create', maxUsd, `Created with budget ceiling: $${maxUsd.toFixed(4)}`);
  }

  public recordUsage(mandateId: string, actualCost: number): void {
    if (actualCost <= 0) return;

    const stmt = this.db.prepare(`
      UPDATE mandates
      SET spent_usd = spent_usd + ?, updated_at = CURRENT_TIMESTAMP
      WHERE id = ?
    `);
    stmt.run(actualCost, mandateId);
    this._logAudit(mandateId, 'spend', actualCost, `Metered actual LLM cost: $${actualCost.toFixed(6)}`);
  }

  public exhaustMandate(mandateId: string): void {
    const stmt = this.db.prepare(`UPDATE mandates SET status = 'exhausted', updated_at = CURRENT_TIMESTAMP WHERE id = ?`);
    stmt.run(mandateId);
    this._logAudit(mandateId, 'exhaust', 0.0, 'Mandate exhausted and locked.');
  }

  public isExpired(mandateId: string): boolean {
    const mandate = this.getMandate(mandateId);
    if (!mandate.expires_at) return false;

    if (new Date() > new Date(mandate.expires_at) && mandate.status === 'active') {
      const stmt = this.db.prepare(`UPDATE mandates SET status = 'expired', updated_at = CURRENT_TIMESTAMP WHERE id = ?`);
      stmt.run(mandateId);
      this._logAudit(mandateId, 'expire', 0.0, 'Mandate automatically expired.');
      return true;
    }
    return mandate.status === 'expired';
  }
}
