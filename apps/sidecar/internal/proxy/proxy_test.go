package proxy_test

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"github.com/ZolileN/mintry-fabric/apps/sidecar/internal/ledger"
	"github.com/ZolileN/mintry-fabric/apps/sidecar/internal/proxy"
)

func TestHealthz(t *testing.T) {
	dir := t.TempDir()
	l, err := ledger.Open(filepath.Join(dir, "vouchers.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()

	srv := proxy.New(proxy.Config{Addr: "127.0.0.1:0"}, l)
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rr := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rr, req)
	if rr.Code != 200 {
		t.Fatalf("status=%d", rr.Code)
	}
}

func TestAuthorizeBlocksBeforeUpstream(t *testing.T) {
	dir := t.TempDir()
	l, err := ledger.Open(filepath.Join(dir, "vouchers.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	if err := l.UpsertMandate("broke", 0.005); err != nil {
		t.Fatal(err)
	}

	upstreamHits := 0
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamHits++
		_ = json.NewEncoder(w).Encode(map[string]any{
			"usage": map[string]int{"prompt_tokens": 10, "completion_tokens": 5},
		})
	}))
	defer upstream.Close()

	// Point absolute URL at upstream host — use 127.0.0.1 which is in llmHosts.
	srv := proxy.New(proxy.Config{DefaultMandate: "broke"}, l)
	body := `{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}`
	abs := upstream.URL + "/v1/chat/completions"
	req := httptest.NewRequest(http.MethodPost, abs, strings.NewReader(body))
	req.Header.Set("X-Mintry-Mandate", "broke")
	rr := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rr, req)

	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402, got %d body=%s", rr.Code, rr.Body.String())
	}
	if upstreamHits != 0 {
		t.Fatalf("upstream should not be hit when blocked")
	}
}

func TestMeteredAllow(t *testing.T) {
	dir := t.TempDir()
	l, err := ledger.Open(filepath.Join(dir, "vouchers.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	if err := l.UpsertMandate("rich", 10.0); err != nil {
		t.Fatal(err)
	}

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"choices": []any{},
			"usage":   map[string]int{"prompt_tokens": 1000, "completion_tokens": 500},
		})
	}))
	defer upstream.Close()

	srv := proxy.New(proxy.Config{}, l)
	body := `{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}`
	abs := upstream.URL + "/v1/chat/completions"
	req := httptest.NewRequest(http.MethodPost, abs, strings.NewReader(body))
	req.Header.Set("X-Mintry-Mandate", "rich")
	rr := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rr, req)

	if rr.Code != 200 {
		b, _ := io.ReadAll(rr.Body)
		t.Fatalf("expected 200, got %d body=%s", rr.Code, b)
	}
	m, err := l.GetMandate("rich")
	if err != nil {
		t.Fatal(err)
	}
	if m.SpentUSD <= 0 {
		t.Fatalf("expected spend recorded, got %v", m.SpentUSD)
	}
}
