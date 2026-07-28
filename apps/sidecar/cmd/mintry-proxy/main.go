// Command mintry-proxy is the Phase 2 Mintry Fabric sidecar (ADR-003).
//
//   HTTP_PROXY=http://127.0.0.1:8820 HTTPS_PROXY=http://127.0.0.1:8820
//
// Enforcement is synchronous against the local SQLite ledger only.
package main

import (
	"flag"
	"log"
	"os"

	"github.com/ZolileN/mintry-fabric/apps/sidecar/internal/ledger"
	"github.com/ZolileN/mintry-fabric/apps/sidecar/internal/proxy"
)

func main() {
	addr := flag.String("addr", envOr("MINTRY_PROXY_ADDR", "127.0.0.1:8820"), "listen address")
	dbPath := flag.String("db", envOr("MINTRY_DB_PATH", ""), "path to vouchers.db (default ~/.mintry/vouchers.db)")
	defaultMandate := flag.String("mandate", envOr("MINTRY_DEFAULT_MANDATE", "customer_support_agent"), "fallback X-Mintry-Mandate")
	flag.Parse()

	l, err := ledger.Open(*dbPath)
	if err != nil {
		log.Fatalf("open ledger: %v", err)
	}
	defer l.Close()

	srv := proxy.New(proxy.Config{
		Addr:                *addr,
		DefaultMandate:      *defaultMandate,
		AllowUninspectedTLS: os.Getenv("MINTRY_ALLOW_UNINSPECTED_HTTPS") == "1",
	}, l)

	if err := srv.ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
