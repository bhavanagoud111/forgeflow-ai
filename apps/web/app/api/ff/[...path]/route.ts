import type { NextRequest } from "next/server";
import {
  FORWARDED_REQUEST_HEADERS,
  FORWARDED_RESPONSE_HEADERS,
  buildUpstreamPath,
  upstreamBaseUrl,
} from "@/lib/proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Context = { params: Promise<{ path: string[] }> };

function errorResponse(status: number, code: string, message: string) {
  return Response.json({ error: { code, message, details: null } }, { status, headers: { "cache-control": "no-store" } });
}

async function proxy(request: NextRequest, context: Context): Promise<Response> {
  const { path } = await context.params;
  const upstreamPath = buildUpstreamPath(path);
  if (!upstreamPath) return errorResponse(404, "not_found", "Unknown API path");

  const token = process.env.FORGEFLOW_API_TOKEN;
  if (!token) {
    return errorResponse(500, "proxy_not_configured", "FORGEFLOW_API_TOKEN is not set on the web server");
  }

  const target = `${upstreamBaseUrl(process.env.FORGEFLOW_API_URL)}${upstreamPath}${request.nextUrl.search}`;

  // Build headers from an allow-list: browser cookies and credentials are never forwarded.
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("authorization", `Bearer ${token}`);

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: request.signal,
    });
  } catch (err) {
    if (request.signal.aborted) return new Response(null, { status: 499 });
    const message = err instanceof Error ? err.message : "connection failed";
    return errorResponse(502, "upstream_unavailable", `ForgeFlow API is unreachable: ${message}`);
  }

  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  const isStream = (upstream.headers.get("content-type") ?? "").includes("text/event-stream");
  if (isStream) {
    responseHeaders.set("cache-control", "no-cache, no-transform");
    responseHeaders.set("x-accel-buffering", "no");
  } else if (!responseHeaders.has("cache-control")) {
    responseHeaders.set("cache-control", "no-store");
  }

  // Pass the body through unbuffered so server-sent events stream to the browser.
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export function GET(request: NextRequest, context: Context) {
  return proxy(request, context);
}

export function POST(request: NextRequest, context: Context) {
  return proxy(request, context);
}

export function DELETE(request: NextRequest, context: Context) {
  return proxy(request, context);
}
