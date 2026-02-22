<script lang="ts">
	import { getContext, createEventDispatcher } from 'svelte';
	import { user } from '$lib/stores';
	import { retryJob } from '$lib/apis/jobs';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	// Props
	export let job: any = null;      // null = closed
	export let isAdmin: boolean = false;

	let retrying = false;
	let retryError = '';

	const STATUS_COLOR: Record<string, string> = {
		completed: 'text-emerald-500',
		running:   'text-blue-400',
		queued:    'text-yellow-400',
		failed:    'text-red-500',
		cancelled: 'text-gray-400'
	};

	const STATUS_DOT: Record<string, string> = {
		completed: 'bg-emerald-500',
		running:   'bg-blue-400',
		queued:    'bg-yellow-400',
		failed:    'bg-red-500',
		cancelled: 'bg-gray-400'
	};

	function close() { dispatch('close'); }

	function fmt(ts: number) {
		if (!ts) return '—';
		return new Date(ts * 1000).toLocaleString();
	}

	function duration(created: number, updated: number) {
		if (!created || !updated) return '—';
		const s = updated - created;
		if (s < 60) return `${s}s`;
		const m = Math.floor(s / 60), rest = s % 60;
		return `${m}m ${rest}s`;
	}

	async function handleRetry() {
		if (!$user?.token || !job) return;
		retrying = true;
		retryError = '';
		const res = await retryJob($user.token, job.job_id);
		retrying = false;
		if (res) {
			dispatch('retried', res);
		} else {
			retryError = 'Retry failed — check server logs.';
		}
	}

	// JSON pretty-print (truncated for safety)
	function pretty(obj: any) {
		if (!obj) return '';
		try {
			return JSON.stringify(obj, null, 2);
		} catch {
			return String(obj);
		}
	}

	// Collapsible sections
	let showRequest = false;
	let showResult = false;
</script>

<!-- Backdrop -->
{#if job}
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div
		class="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity"
		role="button"
		tabindex="-1"
		on:click={close}
	/>

	<!-- Drawer panel -->
	<div
		class="fixed right-0 top-0 z-50 h-full w-full max-w-xl bg-white dark:bg-gray-900 shadow-2xl flex flex-col border-l border-gray-200 dark:border-gray-800 transition-transform"
	>
		<!-- Header -->
		<div class="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-gray-800">
			<div>
				<p class="text-xs text-gray-400 font-mono">{job.job_id?.slice(0, 16)}…</p>
				<h3 class="text-base font-semibold text-gray-800 dark:text-gray-100">
					{job.model_id ?? $i18n.t('Job Detail')}
				</h3>
			</div>
			<button
				class="rounded-lg p-2 hover:bg-gray-100 dark:hover:bg-gray-800 transition text-gray-500"
				on:click={close}
				aria-label="Close"
			>
				<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>
		</div>

		<!-- Scrollable body -->
		<div class="flex-1 overflow-y-auto px-5 py-5 space-y-6">

			<!-- Status + timeline -->
			<div class="rounded-2xl bg-gray-50 dark:bg-gray-800/60 p-4 space-y-3">
				<div class="flex items-center gap-2">
					<span class="inline-block w-2.5 h-2.5 rounded-full {STATUS_DOT[job.status] ?? 'bg-gray-400'}" />
					<span class="text-sm font-semibold capitalize {STATUS_COLOR[job.status] ?? ''}">{job.status}</span>
					{#if job.attempt_count > 0}
						<span class="ml-auto text-xs text-gray-400">{job.attempt_count}/{job.max_attempts} {$i18n.t('attempts')}</span>
					{/if}
				</div>

				<!-- Timeline bar -->
				<div class="space-y-1 text-xs text-gray-500 dark:text-gray-400">
					<div class="flex justify-between">
						<span>{$i18n.t('Created')}</span>
						<span class="font-mono">{fmt(job.created_at)}</span>
					</div>
					<div class="flex justify-between">
						<span>{$i18n.t('Updated')}</span>
						<span class="font-mono">{fmt(job.updated_at)}</span>
					</div>
					<div class="flex justify-between">
						<span>{$i18n.t('Duration')}</span>
						<span class="font-mono">{duration(job.created_at, job.updated_at)}</span>
					</div>
					{#if job.backend_url}
						<div class="flex justify-between">
							<span>{$i18n.t('Backend')}</span>
							<span class="font-mono truncate max-w-[200px]">{job.backend_url}</span>
						</div>
					{/if}
				</div>
			</div>

			<!-- Error banner -->
			{#if job.error}
				<div class="rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4">
					<p class="text-xs font-semibold text-red-600 dark:text-red-400 mb-1">{$i18n.t('Error')}</p>
					<pre class="text-xs text-red-700 dark:text-red-300 whitespace-pre-wrap break-words">{job.error}</pre>
				</div>
			{/if}

			<!-- Retry button (admin + terminal) -->
			{#if isAdmin && (job.status === 'failed' || job.status === 'cancelled')}
				<div>
					<button
						class="w-full rounded-xl px-4 py-2.5 text-sm font-medium bg-indigo-600 hover:bg-indigo-700 text-white transition disabled:opacity-60"
						disabled={retrying}
						on:click={handleRetry}
					>
						{#if retrying}
							<span class="animate-pulse">{$i18n.t('Re-queuing…')}</span>
						{:else}
							↻ {$i18n.t('Retry Job')}
						{/if}
					</button>
					{#if retryError}
						<p class="mt-1.5 text-xs text-red-500 text-center">{retryError}</p>
					{/if}
				</div>
			{/if}

			<!-- Request JSON -->
			<div class="border border-gray-100 dark:border-gray-800 rounded-xl overflow-hidden">
				<button
					class="w-full flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-gray-800/60 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
					on:click={() => showRequest = !showRequest}
				>
					<span>{$i18n.t('Request Payload')}</span>
					<span class="text-gray-400">{showRequest ? '▲' : '▼'}</span>
				</button>
				{#if showRequest}
					<pre class="p-4 text-xs text-gray-600 dark:text-gray-400 overflow-auto max-h-64 bg-white dark:bg-gray-900">{pretty(job.request ?? job)}</pre>
				{/if}
			</div>

			<!-- Result JSON -->
			{#if job.result}
				<div class="border border-gray-100 dark:border-gray-800 rounded-xl overflow-hidden">
					<button
						class="w-full flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-gray-800/60 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
						on:click={() => showResult = !showResult}
					>
						<span>{$i18n.t('Result')}</span>
						<span class="text-gray-400">{showResult ? '▲' : '▼'}</span>
					</button>
					{#if showResult}
						<pre class="p-4 text-xs text-gray-600 dark:text-gray-400 overflow-auto max-h-80 bg-white dark:bg-gray-900">{pretty(job.result)}</pre>
					{/if}
				</div>
			{/if}

		</div>
	</div>
{/if}
