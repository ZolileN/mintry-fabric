// tools/gemini-mock-server/main.go
//
// Mintry Fabric — Gemini Mock Server
//
// A minimal, zero-external-dependency HTTP server that mimics the upstream
// Google Gemini API. Every request incurs a hardcoded 10 ms synthetic delay
// so that any additional latency observed during proxy testing is attributable
// solely to Mintry's internal execution.
//
// Usage:
//   go run main.go              # listens on :9090
//   go run main.go -addr :9091  # custom address

package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"strings"
	"sync/atomic"
	"time"
)

// ---------------------------------------------------------------------------
// Hardcoded Gemini response payload (deterministic — never changes).
// ---------------------------------------------------------------------------

type GeminiCandidate struct {
	Content       GeminiContent `json:"content"`
	FinishReason  string        `json:"finishReason"`
	Index         int           `json:"index"`
	SafetyRatings []interface{} `json:"safetyRatings"`
}

type GeminiContent struct {
	Parts []GeminiPart `json:"parts"`
	Role  string       `json:"role"`
}

type GeminiPart struct {
	Text string `json:"text"`
}

type GeminiUsage struct {
	PromptTokenCount     int `json:"promptTokenCount"`
	CandidatesTokenCount int `json:"candidatesTokenCount"`
	TotalTokenCount      int `json:"totalTokenCount"`
}

type GeminiResponse struct {
	Candidates    []GeminiCandidate `json:"candidates"`
	UsageMetadata GeminiUsage       `json:"usageMetadata"`
	ModelVersion  string            `json:"modelVersion"`
}

var staticResponse = GeminiResponse{
	Candidates: []GeminiCandidate{
		{
			Content: GeminiContent{
				Parts: []GeminiPart{
					{Text: "Mintry mock response: the proxy overhead is your only variable."},
				},
				Role: "model",
			},
			FinishReason:  "STOP",
			Index:         0,
			SafetyRatings: []interface{}{},
		},
	},
	UsageMetadata: GeminiUsage{
		PromptTokenCount:     12,
		CandidatesTokenCount: 14,
		TotalTokenCount:      26,
	},
	ModelVersion: "gemini-2.0-flash-mock",
}

// ---------------------------------------------------------------------------
// Synthetic delay constant — this is the control baseline.
// Any latency recorded above this value during proxy tests is pure Mintry
// proxy overhead.
// ---------------------------------------------------------------------------
const syntheticDelay = 10 * time.Millisecond

// ---------------------------------------------------------------------------
// Request counter (atomic-safe).
// ---------------------------------------------------------------------------
var reqCount int64
var verbose bool

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

func generateContentHandler(w http.ResponseWriter, r *http.Request) {
	received := time.Now()

	// Only accept POST requests.
	if r.Method != http.MethodPost {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}

	// Validate the URL pattern: /v1beta/models/<model>:generateContent
	path := r.URL.Path
	if !strings.HasSuffix(path, ":generateContent") {
		http.Error(w, "Not Found", http.StatusNotFound)
		return
	}

	// Apply deterministic synthetic delay — our control baseline.
	time.Sleep(syntheticDelay)

	// Serialize the static response.
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)

	if err := json.NewEncoder(w).Encode(staticResponse); err != nil {
		log.Printf("[ERROR] failed to encode response: %v", err)
		return
	}

	currentReq := atomic.AddInt64(&reqCount, 1)
	if verbose {
		elapsed := time.Since(received)
		log.Printf("[MOCK] req=%d  path=%-55s  status=200  duration=%s",
			currentReq, path, elapsed.Round(time.Microsecond))
	}
}

// Health check — useful for k6 warm-up assertions.
func healthHandler(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintln(w, `{"status":"ok","server":"gemini-mock","delay_ms":10}`)
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

func main() {
	addr := flag.String("addr", ":9090", "TCP address to listen on")
	flag.BoolVar(&verbose, "verbose", false, "Enable verbose request logging")
	flag.Parse()

	mux := http.NewServeMux()
	mux.HandleFunc("/v1beta/models/", generateContentHandler)
	mux.HandleFunc("/health", healthHandler)

	log.Printf("🚀 Gemini Mock Server listening on %s", *addr)
	log.Printf("   Synthetic upstream delay : %s (control baseline)", syntheticDelay)
	log.Printf("   Health check             : http://localhost%s/health", *addr)
	log.Printf("   Endpoint pattern         : POST /v1beta/models/<model>:generateContent")
	log.Println("   Any measured latency above 10ms is pure Mintry proxy overhead.")

	server := &http.Server{
		Addr:         *addr,
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("[FATAL] server error: %v", err)
	}
}
