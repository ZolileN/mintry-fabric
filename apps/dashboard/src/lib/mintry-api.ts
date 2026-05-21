const DEFAULT_API_ORIGIN = "http://127.0.0.1:8000";

function getApiOrigin(): string {
  return process.env.MINTRY_DASHBOARD_API_ORIGIN || DEFAULT_API_ORIGIN;
}

function buildApiUrl(path: string): string {
  return new URL(path, getApiOrigin()).toString();
}

export async function proxyMintryGet(path: string): Promise<Response> {
  const upstream = await fetch(buildApiUrl(path), {
    cache: "no-store",
  });

  const body = await upstream.text();

  return new Response(body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") || "application/json",
      "cache-control": "no-store",
    },
  });
}

export async function proxyMintryPost(
  path: string,
  request: Request,
): Promise<Response> {
  const payload = await request.text();
  const upstream = await fetch(buildApiUrl(path), {
    method: "POST",
    headers: {
      "content-type": request.headers.get("content-type") || "application/json",
    },
    body: payload,
    cache: "no-store",
  });

  const body = await upstream.text();

  return new Response(body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") || "application/json",
      "cache-control": "no-store",
    },
  });
}
