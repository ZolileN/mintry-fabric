# Multi-stage Alpine build for mintry-proxy (ADR-003).
# Uses pure-Go SQLite (modernc.org/sqlite) — no CGO required.

FROM golang:1.22-alpine AS builder
WORKDIR /src
RUN apk add --no-cache git ca-certificates
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/mintry-proxy ./cmd/mintry-proxy

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /out/mintry-proxy /usr/local/bin/mintry-proxy
ENV MINTRY_PROXY_ADDR=0.0.0.0:8820
ENV MINTRY_DB_PATH=/data/vouchers.db
EXPOSE 8820
VOLUME ["/data"]
ENTRYPOINT ["/usr/local/bin/mintry-proxy"]
