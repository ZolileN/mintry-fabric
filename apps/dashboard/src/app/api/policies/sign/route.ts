import { NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import {
  allowMockSignatures,
  requirePolicySignatures,
  resolvePolicyPrivateKey,
  signPolicyBundleCanonical,
} from '@/lib/policy-crypto';
import { requireDashboardAuth } from '@/lib/auth';

const supabaseUrl = process.env.MINTRY_CONTROL_PLANE_URL || '';
const supabaseServiceKey =
  process.env.MINTRY_SERVICE_ROLE_KEY || process.env.MINTRY_CONTROL_PLANE_KEY || '';

export async function POST(request: Request) {
  const auth = await requireDashboardAuth(request);
  if (!auth.ok) {
    return auth.response;
  }

  try {
    if (!supabaseUrl || !supabaseServiceKey) {
      return NextResponse.json(
        { error: 'Control plane is not configured' },
        { status: 503 }
      );
    }

    const supabase = createClient(supabaseUrl, supabaseServiceKey);
    const body = await request.json();
    const { agent_id, mandates } = body;

    if (!agent_id || !mandates) {
      return NextResponse.json({ error: 'Missing agent_id or mandates' }, { status: 400 });
    }

    if (typeof mandates !== 'object' || Array.isArray(mandates)) {
      return NextResponse.json(
        { error: 'mandates must be an object map of mandate_id → {max_usd, ...}' },
        { status: 400 }
      );
    }

    const { data: latestPolicy, error: fetchError } = await supabase
      .from('policy_bundles')
      .select('version')
      .eq('agent_id', agent_id)
      .order('version', { ascending: false })
      .limit(1)
      .single();

    let newVersion = 1;
    if (latestPolicy) {
      newVersion = latestPolicy.version + 1;
    } else if (fetchError && fetchError.code !== 'PGRST116') {
      console.error('Error fetching latest policy:', fetchError);
      return NextResponse.json({ error: 'Failed to fetch latest policy' }, { status: 500 });
    }

    const issuedAt = new Date().toISOString();
    const issuedBy = auth.subject || 'vercel_dashboard_signer';

    const signingPayload = {
      version: newVersion,
      mandates,
      issued_at: issuedAt,
      issued_by: issuedBy,
    };

    const privateKey = resolvePolicyPrivateKey();
    let signature: string;

    if (privateKey) {
      signature = signPolicyBundleCanonical(signingPayload, privateKey);
    } else if (allowMockSignatures() && !requirePolicySignatures()) {
      console.warn('[mintry] Signing with mock signature (MINTRY_ALLOW_MOCK_SIGNATURES=1)');
      signature = 'mock_signature_for_phase2_spike';
    } else {
      return NextResponse.json(
        {
          error:
            'MINTRY_POLICY_PRIVATE_KEY is required to sign policies. ' +
            'For local spike-only use set MINTRY_ALLOW_MOCK_SIGNATURES=1.',
        },
        { status: 500 }
      );
    }

    const fullBundle = {
      ...signingPayload,
      signature,
    };

    const { error: insertError } = await supabase.from('policy_bundles').insert([
      {
        agent_id,
        version: newVersion,
        policy_json: mandates,
        signature,
        issued_at: issuedAt,
        issued_by: issuedBy,
      },
    ]);

    if (insertError) {
      console.error('Error inserting policy:', insertError);
      return NextResponse.json({ error: 'Failed to save policy to control plane' }, { status: 500 });
    }

    return NextResponse.json({
      success: true,
      version: newVersion,
      bundle: fullBundle,
    });
  } catch (error) {
    console.error('Policy signer error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
