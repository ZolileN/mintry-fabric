package ledger_test

import (
	"path/filepath"
	"testing"

	"github.com/ZolileN/mintry-fabric/apps/sidecar/internal/ledger"
)

func TestAuthorizeBlocksWhenExhausted(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "vouchers.db")
	l, err := ledger.Open(dbPath)
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()

	if err := l.UpsertMandate("agent_a", 1.00); err != nil {
		t.Fatal(err)
	}

	d := l.Authorize("agent_a")
	if !d.Allow {
		t.Fatalf("expected allow with headroom, got %#v", d)
	}

	if err := l.RecordSpend("agent_a", 0.995, "consume"); err != nil {
		t.Fatal(err)
	}
	d = l.Authorize("agent_a")
	if d.Allow || d.Reason != "budget_exhausted" {
		t.Fatalf("expected budget_exhausted, got %#v", d)
	}
}

func TestAuthorizeUnknownMandate(t *testing.T) {
	dir := t.TempDir()
	l, err := ledger.Open(filepath.Join(dir, "vouchers.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()

	d := l.Authorize("missing")
	if d.Allow || d.Reason != "unknown_mandate" {
		t.Fatalf("expected unknown_mandate, got %#v", d)
	}
}
