# ForgeFlow AI web console

Next.js (App Router) frontend for the ForgeFlow AI API: dashboard, agent control center, live execution
view with the workflow graph, diff viewer, repositories, approvals and settings.

## Running locally

Requirements: Node.js 20.9+ (22 or 24 recommended) and a running ForgeFlow API (default `http://localhost:8000`).

```bash
cd apps/web
cp .env.example .env.local      # then set FORGEFLOW_API_TOKEN
npm install
npm run dev                     # http://localhost:3000
```

Production build:

```bash
npm run build
node .next/standalone/server.js # or: docker build -t forgeflow-web . && docker run -p 3000:3000 --env-file .env.local forgeflow-web
```

When running the standalone server directly, copy `.next/static` into `.next/standalone/.next/static` first
(the Dockerfile does this).

## Environment variables

| Variable              | Default                 | Purpose                                                    |
| --------------------- | ----------------------- | ---------------------------------------------------------- |
| `FORGEFLOW_API_URL`   | `http://localhost:8000` | Base URL of the ForgeFlow API. Server-side only.           |
| `FORGEFLOW_API_TOKEN` | (none, required)        | Bearer token the proxy adds to every request. Server-side. |

Neither variable uses the `NEXT_PUBLIC_` prefix, so neither is bundled into client code.

## Scripts

| Command             | What it does                    |
| ------------------- | ------------------------------- |
| `npm run dev`       | Development server on port 3000 |
| `npm run build`     | Production build (standalone)   |
| `npm run start`     | `next start` on port 3000       |
| `npm run lint`      | ESLint                          |
| `npm run typecheck` | `tsc --noEmit`                  |
| `npm test`          | Vitest unit tests               |

## Architecture

### API proxy

The browser never sees the API token. All client requests go to `/api/ff/<backend path>`, handled by
`app/api/ff/[...path]/route.ts`, which:

- accepts `GET`, `POST` and `DELETE`;
- only forwards paths that start with `api/` and rejects traversal or encoded separators (`lib/proxy.ts`);
- builds outgoing headers from an allow-list (`accept`, `content-type`, `last-event-id`), so browser cookies
  and any browser-supplied `Authorization` header are dropped, then adds `Authorization: Bearer $FORGEFLOW_API_TOKEN`;
- returns the upstream body as a stream, so `text/event-stream` responses are relayed unbuffered
  (`cache-control: no-cache, no-transform`, `x-accel-buffering: no`);
- maps connection failures to `502 {"error": {"code": "upstream_unavailable", ...}}`, matching the API's error shape.

### Live execution updates

`lib/hooks/use-execution-events.ts` opens an `EventSource` on
`/api/ff/api/executions/{id}/events`:

- every event carries `id: <seq>`; `mergeEvents` (`lib/events.ts`) keeps events ordered and ignores any
  `seq` at or below the last one seen, so replays after a reconnect never duplicate entries;
- `EventSource` reconnects on network errors and sends `Last-Event-ID`, which the proxy forwards. If the
  browser gives up (for example an HTTP error), the hook reopens with `?after=<last seq>`;
- the stream is closed on the server's `stream.end` event;
- key events invalidate the related React Query caches in small batches (execution detail, trace, diff,
  lists, metrics, approvals, agents) — see `cacheKeysForEvent`.

Node states in the workflow graph are derived from the same event stream (`lib/node-status.ts`), and the
graph layout is a small layered top-to-bottom layout (`lib/graph-layout.ts`) that detects retry loops as
back edges.

### Project layout

```
app/                    routes (server components that render client views) and the proxy route
components/ui/          local UI primitives (Button, Card, Badge, Tabs, Dialog, Table, Select, ...)
components/<feature>/   dashboard, agents, executions, diff, repositories, approvals, settings
lib/                    API client, query hooks, types and pure logic (diff parser, layout, events)
tests/                  Vitest unit tests for the pure modules
```

### Simulated output

When the API reports the deterministic demo model provider (`health.simulated_llm` or
`execution.simulated`), the UI shows a "Simulated model output (demo provider)" badge. All numbers, events
and statuses come from the API; nothing is generated in the browser.
