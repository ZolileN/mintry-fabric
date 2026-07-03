import { NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import crypto from 'crypto';

// Use environment variables for Supabase connection
const supabaseUrl = process.env.MINTRY_CONTROL_PLANE_URL || 'https://wudyreicddrqdysplxai.supabase.co';
const supabaseServiceKey = process.env.MINTRY_SERVICE_ROLE_KEY || process.env.MINTRY_CONTROL_PLANE_KEY || 'dummy_key_to_prevent_crash_on_load';

const supabase = createClient(supabaseUrl, supabaseServiceKey);

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { agent_id, mandates } = body;

    if (!agent_id || !mandates) {
      return NextResponse.json({ error: 'Missing agent_id or mandates' }, { status: 400 });
    }

    // 1. Get current version from Supabase
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

    // 2. Prepare the policy bundle
    const issuedAt = new Date().toISOString();
    const issuedBy = 'vercel_dashboard_signer';
    
    const signingPayload = {
      version: newVersion,
      mandates,
      issued_at: issuedAt,
      issued_by: issuedBy
    };

    // 3. Cryptographically sign the bundle (Mocked for spike if no key)
    let signature = 'mock_signature_for_phase2_spike';
    const privateKey = process.env.MINTRY_PRIVATE_KEY;
    if (privateKey) {
      const message = Buffer.from(JSON.stringify(signingPayload));
      const sign = crypto.createSign('SHA256');
      sign.update(message);
      signature = sign.sign(privateKey, 'base64');
    }

    const fullBundle = {
      ...signingPayload,
      signature
    };

    // 4. Insert into Supabase
    const { error: insertError } = await supabase
      .from('policy_bundles')
      .insert([
        {
          agent_id,
          version: newVersion,
          policy_json: mandates,
          signature,
          issued_at: issuedAt,
          issued_by: issuedBy
        }
      ]);

    if (insertError) {
      console.error('Error inserting policy:', insertError);
      return NextResponse.json({ error: 'Failed to save policy to control plane' }, { status: 500 });
    }

    return NextResponse.json({ 
      success: true, 
      version: newVersion,
      bundle: fullBundle
    });

  } catch (error) {
    console.error('Policy signer error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
