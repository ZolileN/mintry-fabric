// Package proxy implements the Mintry explicit HTTP forward proxy.
//
// Hot path: authorize against the local SQLite ledger, then forward.
// No control-plane network I/O on allow/block (Principle 3).
//
// HTTPS CONNECT is tunnelled without body inspection in this scaffold
// (MITM TLS termination is a follow-up). Plain HTTP absolute-form and
// gateway absolute URLs are fully governed and metered.
package proxy

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"strings"
	"time"

	"github.com/ZolileN/mintry-fabric/apps/sidecar/internal/intent"
	"github.com/ZolileN/mintry-fabric/apps/sidecar/internal/ledger"
	"github.com/ZolileN/mintry-fabric/apps/sidecar/internal/pricing"
)

var llmHosts = []string{
	"api.openai.com",
	"api.anthropic.com",
	"generativelanguage.googleapis.com",
	"api.mistral.ai",
	"127.0.0.1",
	"localhost",
}

// Config controls proxy listen behaviour.
type Config struct {
	Addr                 string
	AllowUninspectedTLS  bool
	DefaultMandate       string
}

type Server struct {
	cfg    Config
	ledger *ledger.Ledger
	client *http.Client
}

func New(cfg Config, l *ledger.Ledger) *Server {
	if cfg.Addr == "" {
		cfg.Addr = "127.0.0.1:8820"
	}
	if cfg.DefaultMandate == "" {
		cfg.DefaultMandate = "customer_support_agent"
	}
	return &Server{
		cfg:    cfg,
		ledger: l,
		client: &http.Client{Timeout: 120 * time.Second},
	}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"ok":      true,
			"service": "mintry-proxy",
			"ledger":  s.ledger.Path(),
		})
	})
	mux.HandleFunc("/", s.handleProxy)
	return mux
}

func (s *Server) ListenAndServe() error {
	log.Printf("mintry-proxy listening on %s (ledger=%s)", s.cfg.Addr, s.ledger.Path())
	return http.ListenAndServe(s.cfg.Addr, s.Handler())
}

func (s *Server) handleProxy(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodConnect {
		s.handleConnect(w, r)
		return
	}

	targetURL := r.URL
	if !targetURL.IsAbs() {
		http.Error(w, "mintry-proxy expects absolute-form HTTP URLs or CONNECT", http.StatusBadRequest)
		return
	}

	host := targetURL.Hostname()
	if !isLLMHost(host) {
		// Non-LLM: pass through without governance.
		s.forwardRaw(w, r)
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "failed to read body", http.StatusBadRequest)
		return
	}
	_ = r.Body.Close()

	mandateID := r.Header.Get("X-Mintry-Mandate")
	if mandateID == "" {
		mandateID = s.cfg.DefaultMandate
	}

	if reason := intent.Check(body); reason != "" {
		_ = s.ledger.LogDecision(mandateID, "block", 0, "Prohibited intent detected — security violation")
		http.Error(w, "Mintry Logic Fabric: Prohibited Intent Detected (Security Violation).", http.StatusForbidden)
		return
	}

	decision := s.ledger.Authorize(mandateID)
	if !decision.Allow {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusPaymentRequired)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"error":      "mintry_mandate_exceeded",
			"reason":     decision.Reason,
			"mandate_id": mandateID,
			"budget_usd": decision.Budget,
			"spent_usd":  decision.Spent,
		})
		return
	}

	outReq, err := http.NewRequestWithContext(r.Context(), r.Method, targetURL.String(), bytes.NewReader(body))
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	copyHeaders(outReq.Header, r.Header)
	outReq.Header.Del("Proxy-Connection")
	outReq.Header.Del("Proxy-Authorization")

	resp, err := s.client.Do(outReq)
	if err != nil {
		http.Error(w, fmt.Sprintf("upstream error: %v", err), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		http.Error(w, "failed to read upstream body", http.StatusBadGateway)
		return
	}

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		model := extractModel(targetURL.String(), body)
		inTok, outTok := extractTokens(respBody)
		cost := pricing.CalculateCost(model, inTok, outTok)
		if cost < 0.000001 {
			cost = 0.002 // base fee fallback matching Python when usage missing
		}
		_ = s.ledger.RecordSpend(mandateID, cost, fmt.Sprintf("sidecar metered model=%s tokens=%d/%d", model, inTok, outTok))
		logJSON("spend_metered", map[string]any{
			"mandate_id": mandateID,
			"model":      model,
			"cost_usd":   cost,
			"prompt_tokens": inTok,
			"completion_tokens": outTok,
		})
	}

	copyHeaders(w.Header(), resp.Header)
	w.WriteHeader(resp.StatusCode)
	_, _ = w.Write(respBody)
}

func (s *Server) handleConnect(w http.ResponseWriter, r *http.Request) {
	host := r.Host
	hostname, _, err := net.SplitHostPort(host)
	if err != nil {
		hostname = host
	}

	if isLLMHost(hostname) && !s.cfg.AllowUninspectedTLS {
		http.Error(w,
			"mintry-proxy: HTTPS CONNECT to LLM hosts requires MITM (not in this scaffold). "+
				"Use HTTP absolute-form against a mock/upstream, or set MINTRY_ALLOW_UNINSPECTED_HTTPS=1 to tunnel without metering.",
			http.StatusNotImplemented)
		return
	}

	dest, err := net.DialTimeout("tcp", host, 10*time.Second)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	hijacker, ok := w.(http.Hijacker)
	if !ok {
		_ = dest.Close()
		http.Error(w, "hijacking not supported", http.StatusInternalServerError)
		return
	}
	clientConn, _, err := hijacker.Hijack()
	if err != nil {
		_ = dest.Close()
		http.Error(w, err.Error(), http.StatusServiceUnavailable)
		return
	}
	_, _ = clientConn.Write([]byte("HTTP/1.1 200 Connection Established\r\n\r\n"))
	go transfer(dest, clientConn)
	go transfer(clientConn, dest)
}

func (s *Server) forwardRaw(w http.ResponseWriter, r *http.Request) {
	rp := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL = r.URL
			req.Host = r.URL.Host
		},
	}
	rp.ServeHTTP(w, r)
}

func transfer(dst net.Conn, src net.Conn) {
	defer dst.Close()
	defer src.Close()
	_, _ = io.Copy(dst, src)
}

func isLLMHost(host string) bool {
	h := strings.ToLower(host)
	for _, known := range llmHosts {
		if h == known || strings.HasSuffix(h, "."+known) {
			return true
		}
	}
	return false
}

func copyHeaders(dst, src http.Header) {
	for k, vv := range src {
		if strings.EqualFold(k, "Content-Length") {
			continue
		}
		for _, v := range vv {
			dst.Add(k, v)
		}
	}
}

func extractModel(url string, body []byte) string {
	if strings.Contains(url, "/models/") {
		parts := strings.Split(url, "/models/")
		if len(parts) > 1 {
			name := strings.Split(parts[1], ":")[0]
			name = strings.Split(name, "?")[0]
			if name != "" {
				return name
			}
		}
	}
	var payload struct {
		Model string `json:"model"`
	}
	if err := json.Unmarshal(body, &payload); err == nil && payload.Model != "" {
		return payload.Model
	}
	return "unknown"
}

func extractTokens(body []byte) (int, int) {
	var payload map[string]any
	if err := json.Unmarshal(body, &payload); err != nil {
		return 0, 0
	}
	if usage, ok := payload["usage"].(map[string]any); ok {
		return asInt(usage["prompt_tokens"]), asInt(usage["completion_tokens"])
	}
	if usage, ok := payload["usageMetadata"].(map[string]any); ok {
		return asInt(usage["promptTokenCount"]), asInt(usage["candidatesTokenCount"])
	}
	return 0, 0
}

func asInt(v any) int {
	switch t := v.(type) {
	case float64:
		return int(t)
	case int:
		return t
	case json.Number:
		i, _ := t.Int64()
		return int(i)
	default:
		return 0
	}
}

func logJSON(event string, fields map[string]any) {
	fields["event"] = event
	fields["timestamp"] = time.Now().UTC().Format(time.RFC3339)
	b, err := json.Marshal(fields)
	if err != nil {
		return
	}
	log.Print(string(b))
}
