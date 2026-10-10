"use client";

import { useSyncExternalStore } from "react";

function subscribe(callback: () => void) {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
}

/** Current `location.hash` without the leading "#" (empty during server rendering). */
export function useLocationHash(): string {
  return useSyncExternalStore(
    subscribe,
    () => window.location.hash.slice(1),
    () => "",
  );
}
