<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { user } from '$lib/stores';
	import { getJobs, cancelJob } from '$lib/apis/jobs';

	const i18n = getContext('i18n');

	let jobs: any[] = [];
	let total = 0;
	let skip = 0;
	const limit = 20;
	let loading = false;
	let pollInterval: ReturnType<typeof setInterval>;

	// Track jobs that were running/queued so we can toast on completion
	let watchedJobIds = new Set<string>();

	const STATUS_COLORS: Record<string, string> = {
		queued: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
		running: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
		completed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
		failed: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
		cancelled: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
	};

	async function fetchJobs() {
		if (!$user?.token) return;
		const res = await getJobs($user.token, skip, limit);
		if (!res) return;

		const prev = new Map(jobs.map((j) => [j.job_id, j.status]));

		jobs = res.jobs ?? [];
		total = res.total ?? 0;

		// Toast on transition to terminal state
		for (const job of jobs) {
			const prevStatus = prev.get(job.job_id);
			if (
				prevStatus &&
				prevStatus !== job.status &&
				(job.status === 'completed' || job.status === 'failed')
			) {
				if (job.status === 'completed') {
					toast.success(
						`${$i18n.t('Job completed')}: ${job.model_id ?? job.job_id.slice(0, 8)}`
					);
				} else {
					toast.error(
						`${$i18n.t('Job failed')}: ${job.error ?? job.job_id.slice(0, 8)}`
					);
				}
			}
		}
	}

	async function handleCancel(jobId: string) {
		if (!$user?.token) return;
		const res = await cancelJob($user.token, jobId).catch(() => null);
		if (res) {
			toast.info($i18n.t('Job cancelled'));
			await fetchJobs();
		}
	}

	function formatTime(epoch: number) {
		return new Date(epoch * 1000).toLocaleString();
	}

	function elapsed(createdAt: number) {
		const diff = Math.floor(Date.now() / 1000 - createdAt);
		if (diff < 60) return `${diff}s`;
		if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`;
		return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`;
	}

	onMount(async () => {
		loading = true;
		await fetchJobs();
		loading = false;
		pollInterval = setInterval(async () => {
			const active = jobs.some((j) => j.status === 'queued' || j.status === 'running');
			if (active) await fetchJobs();
		}, 5000);
	});

	onDestroy(() => clearInterval(pollInterval));
</script>

<svelte:head>
	<title>My Jobs • Open WebUI</title>
</svelte:head>

<div class="px-4 py-8 max-w-5xl mx-auto w-full">
	<!-- Header -->
	<div class="flex items-center justify-between mb-6">
		<div>
			<h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">{$i18n.t('My Jobs')}</h1>
			<p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
				{$i18n.t('Track your async LLM jobs')}
			</p>
		</div>
		<div class="flex items-center gap-3">
			{#if total > 0}
				<span class="text-xs text-gray-400">{total} {$i18n.t('total')}</span>
			{/if}
			<button
				class="text-sm px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition text-gray-700 dark:text-gray-300 flex items-center gap-1.5"
				on:click={fetchJobs}
			>
				<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
						d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
				</svg>
				{$i18n.t('Refresh')}
			</button>
		</div>
	</div>

	{#if loading}
		<div class="space-y-3">
			{#each Array(4) as _}
				<div class="h-16 rounded-2xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
			{/each}
		</div>
	{:else if jobs.length === 0}
		<div class="flex flex-col items-center justify-center py-32 text-gray-400 dark:text-gray-600">
			<svg class="w-12 h-12 mb-4 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
					d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
			</svg>
			<p class="text-sm font-medium">{$i18n.t('No jobs yet')}</p>
			<p class="text-xs mt-1">{$i18n.t('Submit a chat completion job via the API to get started')}</p>
		</div>
	{:else}
		<!-- Job Cards -->
		<div class="space-y-3">
			{#each jobs as job (job.job_id)}
				<div class="rounded-2xl p-4 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm hover:shadow-md transition">
					<div class="flex items-start justify-between gap-4">
						<!-- Left: model + status -->
						<div class="flex items-center gap-3 min-w-0">
							<div class="flex-shrink-0 w-9 h-9 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
								{#if job.status === 'running'}
									<span class="inline-block w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
								{:else if job.status === 'completed'}
									<svg class="w-4 h-4 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
									</svg>
								{:else if job.status === 'failed'}
									<svg class="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
									</svg>
								{:else if job.status === 'queued'}
									<svg class="w-4 h-4 text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
									</svg>
								{:else}
									<svg class="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
									</svg>
								{/if}
							</div>
							<div class="min-w-0">
								<div class="font-medium text-sm text-gray-800 dark:text-gray-200 truncate">
									{job.model_id ?? 'Unknown model'}
								</div>
								<div class="text-xs text-gray-400 dark:text-gray-500 font-mono">
									{job.job_id.slice(0, 12)}…
								</div>
							</div>
						</div>

						<!-- Right: badge + actions -->
						<div class="flex items-center gap-2 flex-shrink-0">
							<span class="px-2 py-0.5 rounded-full text-xs font-medium {STATUS_COLORS[job.status] ?? ''}">
								{job.status}
							</span>
							{#if job.status === 'queued' || job.status === 'running'}
								<button
									class="text-xs px-2 py-1 rounded-lg text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition"
									on:click={() => handleCancel(job.job_id)}
								>
									{$i18n.t('Cancel')}
								</button>
							{/if}
						</div>
					</div>

					<!-- Footer: timestamps + attempts -->
					<div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500">
						<span>{$i18n.t('Started')} {formatTime(job.created_at)}</span>
						<span>{$i18n.t('Elapsed')}: {elapsed(job.created_at)}</span>
						<span>{$i18n.t('Attempt')} {job.attempt_count}/{job.max_attempts}</span>
						{#if job.error}
							<span class="text-red-400 truncate max-w-xs" title={job.error}>{job.error}</span>
						{/if}
					</div>
				</div>
			{/each}
		</div>

		<!-- Pagination -->
		{#if total > limit}
			<div class="flex items-center justify-between mt-6 text-xs text-gray-400">
				<span>{skip + 1}–{Math.min(skip + limit, total)} {$i18n.t('of')} {total}</span>
				<div class="flex gap-2">
					<button
						class="px-3 py-1 rounded-lg bg-gray-100 dark:bg-gray-800 disabled:opacity-40 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
						disabled={skip === 0}
						on:click={async () => { skip = Math.max(0, skip - limit); await fetchJobs(); }}
					>← {$i18n.t('Prev')}</button>
					<button
						class="px-3 py-1 rounded-lg bg-gray-100 dark:bg-gray-800 disabled:opacity-40 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
						disabled={skip + limit >= total}
						on:click={async () => { skip += limit; await fetchJobs(); }}
					>{$i18n.t('Next')} →</button>
				</div>
			</div>
		{/if}
	{/if}
</div>
