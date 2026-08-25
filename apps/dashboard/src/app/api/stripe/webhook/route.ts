import crypto from "crypto";
import { proxyMintryPost } from "@/lib/mintry-api";

function verifyStripeSignature(
  payload: string,
  signatureHeader: string,
  secret: string,
): boolean {
  const parts = signatureHeader.split(",").map((p) => p.trim());
  const timestamp = parts.find((p) => p.startsWith("t="))?.slice(2);
  const v1 = parts.find((p) => p.startsWith("v1="))?.slice(3);
  if (!timestamp || !v1) return false;
  const signed = crypto
    .createHmac("sha256", secret)
    .update(`${timestamp}.${payload}`)
    .digest("hex");
  try {
    return crypto.timingSafeEqual(Buffer.from(signed), Buffer.from(v1));
  } catch {
    return false;
  }
}

/**
 * Stripe webhook → ledger top-up via Python API (control-plane only).
 * Configure Stripe to send checkout.session.completed with metadata.mandate_id.
 */
export async function POST(request: Request): Promise<Response> {
  const raw = await request.text();
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  const sig = request.headers.get("stripe-signature");

  if (secret) {
    if (!sig || !verifyStripeSignature(raw, sig, secret)) {
      return Response.json({ error: "Invalid Stripe signature" }, { status: 400 });
    }
  } else if (process.env.NODE_ENV === "production") {
    return Response.json({ error: "STRIPE_WEBHOOK_SECRET required" }, { status: 500 });
  }

  let event: { type?: string; data?: { object?: Record<string, unknown> } };
  try {
    event = JSON.parse(raw);
  } catch {
    return Response.json({ error: "Invalid JSON" }, { status: 400 });
  }

  if (event.type !== "checkout.session.completed") {
    return Response.json({ received: true, skipped: event.type }, { status: 200 });
  }

  const session = event.data?.object ?? {};
  const metadata = (session.metadata as Record<string, string>) || {};
  const mandateId = metadata.mandate_id || metadata.mintry_mandate_id;
  const amountTotal = session.amount_total as number | undefined;

  if (!mandateId || amountTotal == null) {
    return Response.json({ error: "Missing mandate_id metadata or amount" }, { status: 400 });
  }

  const amountUsd = amountTotal / 100;
  const topupBody = JSON.stringify({
    mandate_id: mandateId,
    amount_usd: amountUsd,
    source: "stripe",
  });

  const upstream = await proxyMintryPost(
    "/api/topup",
    new Request(request.url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: topupBody,
    }),
  );

  return upstream;
}
