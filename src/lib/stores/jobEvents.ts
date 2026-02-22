/**
 * jobEvents.ts — B1: SSE-based real-time job status store.
 *
 * Connects to GET /api/v1/jobs/events once and dispatches:
 *   - toast notifications on job completed / failed
 *   - updates to the `latestJobEvent` writable store
 *
 * Usage:
 *   import { initJobEvents, latestJobEvent } from '$lib/stores/jobEvents';
 *   // Call once in a top-level +layout.svelte after login:
 *   initJobEvents(token);
 */

import { writable } from 'svelte/store';
import { WEBUI_API_BASE_URL } from '$lib/constants';

export interface JobEvent {
    job_id: string;
    status: 'completed' | 'failed' | 'queued' | 'running' | 'cancelled';
    error?: string;
    updated_at?: number;
}

/** Latest job status event received via SSE. */
export const latestJobEvent = writable<JobEvent | null>(null);

let _source: EventSource | null = null;

/**
 * Open an SSE connection to /api/v1/jobs/events.
 * Call this once after the user logs in.
 * Calling again while already connected is a no-op.
 */
export function initJobEvents(token: string, onEvent?: (e: JobEvent) => void): void {
    if (_source && _source.readyState !== EventSource.CLOSED) return;

    const url = `${WEBUI_API_BASE_URL}/jobs/events`;

    // EventSource doesn't support Authorization headers natively;
    // we append the token as a query param (backend validates via Depends).
    _source = new EventSource(`${url}?token=${encodeURIComponent(token)}`);

    _source.onmessage = (msg) => {
        try {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const raw = JSON.parse(msg.data) as any;
            if (raw.ping) return; // ignore heartbeats

            const event = raw as JobEvent;
            latestJobEvent.set(event);
            onEvent?.(event);
        } catch {
            // malformed event — ignore
        }
    };

    _source.onerror = () => {
        // Auto-retry is handled by the browser's EventSource implementation.
        // Log for debugging only.
        console.debug('[jobEvents] SSE error — browser will reconnect automatically');
    };
}

/** Disconnect SSE (call on logout). */
export function destroyJobEvents(): void {
    _source?.close();
    _source = null;
    latestJobEvent.set(null);
}
