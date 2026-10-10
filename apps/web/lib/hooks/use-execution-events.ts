"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { apiUrl } from "../api";
import {
  EMPTY_EVENT_LOG,
  EVENT_TYPES,
  cacheKeysForEvent,
  mergeEvents,
  parseEventPayload,
  type EventLog,
} from "../events";
import type { ExecutionEvent } from "../types";

export type StreamStatus = "connecting" | "open" | "reconnecting" | "ended" | "error";

export interface ExecutionEventsState {
  events: ExecutionEvent[];
  lastSeq: number;
  status: StreamStatus;
}

const FLUSH_MS = 150;
const INVALIDATE_MS = 400;
const MANUAL_RETRY_MS = 3000;

/**
 * Subscribe to an execution's event stream through the server-side proxy.
 *
 * - Events are merged with `mergeEvents`, which drops anything at or below the
 *   last seen `seq`, so replays after a reconnect never duplicate entries.
 * - EventSource reconnects on its own and sends `Last-Event-ID`; the proxy forwards
 *   it. If the browser gives up (HTTP error), we reopen with `?after=<lastSeq>`.
 * - The stream is closed for good on `stream.end`.
 * - Key events invalidate the related react-query caches (batched).
 *
 * State is per hook instance: callers should key the component by execution id.
 */
export function useExecutionEvents(id: string | null | undefined): ExecutionEventsState {
  const queryClient = useQueryClient();
  const [log, setLog] = useState<EventLog>(EMPTY_EVENT_LOG);
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const lastSeqRef = useRef(0);

  useEffect(() => {
    if (!id) return;
    let source: EventSource | null = null;
    let closed = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let flushTimer: ReturnType<typeof setTimeout> | null = null;
    let invalidateTimer: ReturnType<typeof setTimeout> | null = null;
    let pending: ExecutionEvent[] = [];
    const pendingKeys = new Map<string, string[]>();

    const flush = () => {
      flushTimer = null;
      if (pending.length === 0) return;
      const batch = pending;
      pending = [];
      setLog((prev) => {
        const next = mergeEvents(prev, batch);
        lastSeqRef.current = next.lastSeq;
        return next;
      });
    };

    const flushInvalidations = () => {
      invalidateTimer = null;
      for (const key of pendingKeys.values()) void queryClient.invalidateQueries({ queryKey: key });
      pendingKeys.clear();
    };

    const queue = (event: ExecutionEvent) => {
      if (event.seq <= lastSeqRef.current) return;
      pending.push(event);
      for (const key of cacheKeysForEvent(event.type, id)) pendingKeys.set(JSON.stringify(key), key);
      flushTimer ??= setTimeout(flush, FLUSH_MS);
      if (pendingKeys.size > 0) invalidateTimer ??= setTimeout(flushInvalidations, INVALIDATE_MS);
    };

    const onEvent = (msg: MessageEvent<string>) => {
      const event = parseEventPayload(msg.data);
      if (event) queue(event);
    };

    const end = () => {
      closed = true;
      source?.close();
      if (flushTimer) clearTimeout(flushTimer);
      flush();
      flushInvalidations();
      setStatus("ended");
    };

    const open = () => {
      if (closed) return;
      const after = Math.max(lastSeqRef.current, ...pending.map((e) => e.seq));
      const url = apiUrl(`/api/executions/${encodeURIComponent(id)}/events`, after > 0 ? { after } : undefined);
      const es = new EventSource(url);
      source = es;
      es.onopen = () => setStatus("open");
      es.onmessage = onEvent;
      for (const type of EVENT_TYPES) {
        es.addEventListener(type, (msg) => onEvent(msg as MessageEvent<string>));
      }
      es.addEventListener("stream.end", end);
      es.onerror = () => {
        if (closed) return;
        if (es.readyState === EventSource.CLOSED) {
          // The browser will not retry (e.g. HTTP error). Reopen from the last seq.
          setStatus("error");
          retryTimer = setTimeout(open, MANUAL_RETRY_MS);
        } else {
          setStatus("reconnecting");
        }
      };
    };

    open();

    return () => {
      closed = true;
      source?.close();
      if (retryTimer) clearTimeout(retryTimer);
      if (flushTimer) clearTimeout(flushTimer);
      if (invalidateTimer) clearTimeout(invalidateTimer);
    };
  }, [id, queryClient]);

  return { events: log.events, lastSeq: log.lastSeq, status };
}
