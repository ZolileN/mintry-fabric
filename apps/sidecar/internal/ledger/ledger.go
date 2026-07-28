// Package ledger provides synchronous local SQLite mandate authorize + spend.
// Never performs network I/O — Principle 3 (enforce locally, always).
package ledger

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	_ "modernc.org/sqlite"
)

const minHeadroom = 0.01

// Ledger is a process-local view of the shared Mintry SQLite wallet.
type Ledger struct {
	db   *sql.DB
	mu   sync.Mutex
	path string
}

type Mandate struct {
	ID        string
	MaxUSD    float64
	SpentUSD  float64
	Status    string
	ExpiresAt sql.NullString
}

type Decision struct {
	Allow  bool
	Reason string
	Budget float64
	Spent  float64
}

func Open(dbPath string) (*Ledger, error) {
	if dbPath == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return nil, err
		}
		dbPath = filepath.Join(home, ".mintry", "vouchers.db")
	}
	if err := os.MkdirAll(filepath.Dir(dbPath), 0o755); err != nil {
		return nil, err
	}

	dsn := fmt.Sprintf("file:%s?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)", dbPath)
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)

	l := &Ledger{db: db, path: dbPath}
	if err := l.ensureSchema(); err != nil {
		_ = db.Close()
		return nil, err
	}
	return l, nil
}

func (l *Ledger) Close() error {
	return l.db.Close()
}

func (l *Ledger) Path() string { return l.path }

func (l *Ledger) ensureSchema() error {
	_, err := l.db.Exec(`
CREATE TABLE IF NOT EXISTS mandates (
  id TEXT PRIMARY KEY,
  max_usd REAL,
  spent_usd REAL DEFAULT 0,
  status TEXT DEFAULT 'active',
  expires_at TEXT DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS mandate_audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT DEFAULT (datetime('now')),
  mandate_id TEXT,
  action TEXT,
  amount REAL,
  details TEXT,
  FOREIGN KEY (mandate_id) REFERENCES mandates(id)
);`)
	return err
}

func (l *Ledger) GetMandate(id string) (Mandate, error) {
	var m Mandate
	err := l.db.QueryRow(
		`SELECT id, max_usd, spent_usd, status, expires_at FROM mandates WHERE id = ?`, id,
	).Scan(&m.ID, &m.MaxUSD, &m.SpentUSD, &m.Status, &m.ExpiresAt)
	if err == sql.ErrNoRows {
		return Mandate{ID: id, Status: "unknown"}, nil
	}
	return m, err
}

// Authorize is the hot-path budget check. Synchronous, local only.
func (l *Ledger) Authorize(mandateID string) Decision {
	l.mu.Lock()
	defer l.mu.Unlock()

	m, err := l.GetMandate(mandateID)
	if err != nil {
		return Decision{Allow: false, Reason: "ledger_error"}
	}
	if m.Status == "unknown" {
		_ = l.logDecisionLocked(mandateID, "block", 0, "Unknown mandate")
		return Decision{Allow: false, Reason: "unknown_mandate"}
	}
	if m.ExpiresAt.Valid && m.ExpiresAt.String != "" {
		exp, err := time.Parse(time.RFC3339, m.ExpiresAt.String)
		if err == nil && !time.Now().UTC().Before(exp) {
			_ = l.logDecisionLocked(mandateID, "block", 0, "Mandate expired — request rejected")
			return Decision{Allow: false, Reason: "expired", Budget: m.MaxUSD, Spent: m.SpentUSD}
		}
	}
	if m.Status == "exhausted" || (m.MaxUSD-m.SpentUSD) < minHeadroom {
		_ = l.logDecisionLocked(mandateID, "block", 0,
			fmt.Sprintf("Insufficient headroom ($%.4f remaining)", m.MaxUSD-m.SpentUSD))
		return Decision{Allow: false, Reason: "budget_exhausted", Budget: m.MaxUSD, Spent: m.SpentUSD}
	}
	_ = l.logDecisionLocked(mandateID, "allow", 0, "Authorized by sidecar")
	return Decision{Allow: true, Reason: "ok", Budget: m.MaxUSD, Spent: m.SpentUSD}
}

func (l *Ledger) RecordSpend(mandateID string, amount float64, details string) error {
	l.mu.Lock()
	defer l.mu.Unlock()

	_, err := l.db.Exec(`UPDATE mandates SET spent_usd = spent_usd + ? WHERE id = ?`, amount, mandateID)
	if err != nil {
		return err
	}
	row := l.db.QueryRow(`SELECT max_usd, spent_usd FROM mandates WHERE id = ?`, mandateID)
	var maxUSD, spent float64
	if err := row.Scan(&maxUSD, &spent); err == nil && spent >= maxUSD {
		_, _ = l.db.Exec(`UPDATE mandates SET status = 'exhausted' WHERE id = ?`, mandateID)
	}
	return l.logDecisionLocked(mandateID, "spend", amount, details)
}

func (l *Ledger) LogDecision(mandateID, action string, amount float64, details string) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.logDecisionLocked(mandateID, action, amount, details)
}

func (l *Ledger) logDecisionLocked(mandateID, action string, amount float64, details string) error {
	_, err := l.db.Exec(
		`INSERT INTO mandate_audit_log (mandate_id, action, amount, details) VALUES (?, ?, ?, ?)`,
		mandateID, action, amount, details,
	)
	return err
}

// UpsertMandate is used by tests and local bootstrap.
func (l *Ledger) UpsertMandate(id string, maxUSD float64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	_, err := l.db.Exec(`
INSERT INTO mandates (id, max_usd, spent_usd, status) VALUES (?, ?, 0.0, 'active')
ON CONFLICT(id) DO UPDATE SET max_usd = excluded.max_usd, status = 'active'`, id, maxUSD)
	return err
}
