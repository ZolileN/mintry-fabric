/**
 * Canonical ES256 policy signing — must match Python mintry.core.crypto.
 *
 * Payload fields: version, mandates, issued_at, issued_by
 * Bytes: JSON with recursively sorted object keys, no spaces, UTF-8
 * Alg: ES256 (ECDSA P-256 + SHA-256), base64 DER signature
 */

import crypto from "crypto";

export const CANONICAL_SIGNING_FIELDS = [
  "version",
  "mandates",
  "issued_at",
  "issued_by",
] as const;

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

/** Recursively sort object keys to match Python json.dumps(sort_keys=True). */
export function sortKeysDeep(value: JsonValue): JsonValue {
  if (Array.isArray(value)) {
    return value.map(sortKeysDeep);
  }
  if (value !== null && typeof value === "object") {
    const sorted: { [key: string]: JsonValue } = {};
    for (const key of Object.keys(value).sort()) {
      sorted[key] = sortKeysDeep(value[key]);
    }
    return sorted;
  }
  return value;
}

export function canonicalSigningPayload(bundle: {
  version: number;
  mandates: unknown;
  issued_at: string;
  issued_by: string;
}): Record<string, unknown> {
  return {
    issued_at: bundle.issued_at,
    issued_by: bundle.issued_by,
    mandates: bundle.mandates,
    version: bundle.version,
  };
}

export function canonicalStringify(bundle: {
  version: number;
  mandates: unknown;
  issued_at: string;
  issued_by: string;
}): string {
  const payload = canonicalSigningPayload(bundle);
  return JSON.stringify(sortKeysDeep(payload as JsonValue));
}

function normalizePem(pem: string): string {
  return pem.includes("\\n") ? pem.replace(/\\n/g, "\n") : pem;
}

export function resolvePolicyPrivateKey(): string | undefined {
  const primary = process.env.MINTRY_POLICY_PRIVATE_KEY;
  if (primary) {
    return normalizePem(primary);
  }
  const legacy = process.env.MINTRY_PRIVATE_KEY;
  if (legacy) {
    console.warn(
      "[mintry] MINTRY_PRIVATE_KEY is deprecated; use MINTRY_POLICY_PRIVATE_KEY"
    );
    return normalizePem(legacy);
  }
  return undefined;
}

export function requirePolicySignatures(): boolean {
  if (process.env.MINTRY_REQUIRE_POLICY_SIGNATURES === "1") {
    return true;
  }
  return process.env.NODE_ENV === "production";
}

export function allowMockSignatures(): boolean {
  return process.env.MINTRY_ALLOW_MOCK_SIGNATURES === "1";
}

export function signPolicyBundleCanonical(
  bundle: {
    version: number;
    mandates: unknown;
    issued_at: string;
    issued_by: string;
  },
  privateKeyPem: string
): string {
  const message = Buffer.from(canonicalStringify(bundle), "utf8");
  const sign = crypto.createSign("SHA256");
  sign.update(message);
  sign.end();
  return sign.sign(privateKeyPem, "base64");
}
