<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { user } from '$lib/stores';
	import { getAdminJobs, cancelJob, retryJob, getArchivedJobs, runArchiveSweep, getArchiveConfig } from '$lib/apis/jobs';
	import JobDetailDrawer from './JobDetailDrawer.svelte';

	const i18n = getContext('i18n');

	// ---- Tab state -------------------------------------------------------
	let activeTab: 'live' | 'archive' = 'live';

	// ---- Live jobs -------------------------------------------------------
	let jobs: any[] = [];
	let total = 0;
	let skip = 0;
	const limit = 20;
	let loading = false;
	let pollInterval: ReturnType<typeof setInterval>;

	// Filters (live tab)
	let liveStatusFilter = '';
	let liveModelFilter = '';

	// Detail drawer
	let selectedJob: any = null;

	// ---- Archive ---------------------------------------------------------
	let archiveJobs: any[] = [];
	let archiveTotal = 0;
	let archiveSkip = 0;
	let archiveLoading = false;
	let archiveConfig: any = null;
	let sweepRunning = false;
	let archiveStatusFilter = '';
	let archiveModelFilter = '';

	// ---- Shared ----------------------------------------------------------
	const STATUS_COLORS: Record<string, string> = {
		queued:    'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
		running:   'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
		completed: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
		failed:    'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
		cancelled: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
	};

	function formatTime(epoch: number) {
		return new Date(epoch * 1000).toLocaleString();
	}
	function elapsed(createdAt: number) {
		const diff = Math.floor(Date.now() / 1000 - createdAt);
		if (diff < 60) return `${diff}s`;
		if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`;
		return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`;
	}

	// ---- Live jobs -------------------------------------------------------
	async function fetchJobs() {
		if (!$user?.token) return;
		const res = await getAdminJobs(
			$user.token, skip, limit,
			liveStatusFilter || undefined,
			liveModelFilter || undefined
		);
		if (res) { jobs = res.jobs ?? []; total = res.total ?? 0; }
	}

	async function handleCancel(jobId: string) {
		if (!$user?.token) return;
		await cancelJob($user.token, jobId);
		if (selectedJob?.job_id === jobId) selectedJob = null;
		await fetchJobs();
	}

	async function handleRetried(event: CustomEvent) {
		const updated = event.detail;
		// Update the row in the list
		jobs = jobs.map((j) => (j.job_id === updated.job_id ? updated : j));
		selectedJob = updated;
		toast.success($i18n.t('Job re-queued'));
	}

	function openDrawer(job: any) {
		// Normalise field name (admin list uses job_id; raw list uses id)
		selectedJob = { ...job, job_id: job.job_id ?? job.id };
	}

	// ---- Archive ---------------------------------------------------------
	async function fetchArchive() {
		if (!$user?.token) return;
		archiveLoading = true;
		const res = await getArchivedJobs(
			$user.token, archiveSkip, limit,
			archiveStatusFilter || undefined,
			archiveModelFilter || undefined
		);
		if (res) { archiveJobs = res.jobs ?? []; archiveTotal = res.total ?? 0; }
		archiveLoading = false;
	}
	async function fetchArchiveConfig() {
		if (!$user?.token) return;
		archiveConfig = await getArchiveConfig($user.token);
	}
	async function triggerSweep() {
		if (!$user?.token || sweepRunning) return;
		sweepRunning = true;
		const res = await runArchiveSweep($user.token);
		sweepRunning = false;
		if (res) {
			toast.success(
				`${$i18n.t('Sweep done')} — ${res.archived} ${$i18n.t('archived')}, ${res.purged} ${$i18n.t('purged')}`
			);
			await fetchArchive();
		}
	}

	$: if (activeTab === 'archive') {
		fetchArchive();
		fetchArchiveConfig();
	}

	onMount(async () => {
		loading = true;
		await fetchJobs();
		loading = false;
		pollInterval = setInterval(async () => {
			if (activeTab !== 'live') return;
			const hasActive = jobs.some((j) => j.status === 'queued' || j.status === 'running');
			if (hasActive) await fetchJobs();
		}, 5000);
	});
	onDestroy(() => clearInterval(pollInterval));
</script>

<!-- Detail Drawer (A1) -->
<JobDetailDrawer
	job={selectedJob}
	isAdmin={true}
	on:close={() => (selectedJob = null)}
	on:retried={handleRetried}
/>

<div class="px-4 py-6 max-w-7xl mx-auto w-full space-y-4">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-xl font-semibold text-gray-800 dark:text-gray-100">{$i18n.t('Job Queue')}</h2>
			<p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{$i18n.t('Monitor and manage async LLM jobs')}</p>
		</div>
		<div class="flex items-center gap-2">
			{#if activeTab === 'live'}
				<span class="text-xs text-gray-400">{total} {$i18n.t('total')}</span>
				<button
					class="text-xs px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition text-gray-700 dark:text-gray-300"
					on:click={fetchJobs}>↻ {$i18n.t('Refresh')}</button>
			{:else}
				<span class="text-xs text-gray-400">{archiveTotal} {$i18n.t('archived')}</span>
				<button
					class="text-xs px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition text-gray-700 dark:text-gray-300"
					on:click={fetchArchive}>↻ {$i18n.t('Refresh')}</button>
				<button
					class="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition disabled:opacity-50"
					disabled={sweepRunning}
					on:click={triggerSweep}>
					{sweepRunning ? '…' : '⚡'} {$i18n.t('Run Sweep Now')}
				</button>
			{/if}
		</div>
	</div>

	<!-- Tabs -->
	<div class="flex gap-1 border-b border-gray-200 dark:border-gray-700">
		{#each [{ key: 'live', label: 'Live Jobs' }, { key: 'archive', label: 'Archive' }] as tab}
			<button
				class="px-4 py-2 text-sm font-medium border-b-2 transition -mb-px {activeTab === tab.key
					? 'border-blue-500 text-blue-600 dark:text-blue-400'
					: 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'}"
				on:click={() => (activeTab = tab.key as 'live' | 'archive')}
			>{$i18n.t(tab.label)}</button>
		{/each}
	</div>

	<!-- ================================================================ -->
	<!-- LIVE JOBS TAB                                                      -->
	<!-- ================================================================ -->
	{#if activeTab === 'live'}
		<!-- A4: Filter bar -->
		<div class="flex flex-wrap gap-2 items-center">
			<select
				class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 outline-none"
				bind:value={liveStatusFilter}
				on:change={() => { skip = 0; fetchJobs(); }}
			>
				<option value="">{$i18n.t('All statuses')}</option>
				<option value="queued">queued</option>
				<option value="running">running</option>
				<option value="completed">completed</option>
				<option value="failed">failed</option>
				<option value="cancelled">cancelled</option>
			</select>
			<input
				class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 outline-none"
				placeholder={$i18n.t('Filter by model…')}
				bind:value={liveModelFilter}
				on:input={() => { skip = 0; fetchJobs(); }}
			/>
			<span class="text-xs text-gray-400 ml-auto">{$i18n.t('Click a row to view details')}</span>
		</div>

		{#if loading}
			<div class="space-y-2">
				{#each Array(5) as _}
					<div class="h-14 rounded-xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
				{/each}
			</div>
		{:else if jobs.length === 0}
			<div class="flex flex-col items-center justify-center py-24 text-gray-400 dark:text-gray-600">
				<svg class="w-10 h-10 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 6h16M4 10h16M4 14h10M4 18h6" />
				</svg>
				<p class="text-sm">{$i18n.t('No jobs found')}</p>
			</div>
		{:else}
			<div class="rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
				<table class="w-full text-sm">
					<thead>
						<tr class="bg-gray-50 dark:bg-gray-800/60 text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
							<th class="px-4 py-3 text-left font-medium">ID</th>
							<th class="px-4 py-3 text-left font-medium">{$i18n.t('Model')}</th>
							<th class="px-4 py-3 text-left font-medium">{$i18n.t('Status')}</th>
							<th class="px-4 py-3 text-left font-medium">{$i18n.t('Attempts')}</th>
							<th class="px-4 py-3 text-left font-medium">{$i18n.t('Started')}</th>
							<th class="px-4 py-3 text-left font-medium">{$i18n.t('Elapsed')}</th>
							<th class="px-4 py-3 text-right font-medium">{$i18n.t('Actions')}</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-gray-100 dark:divide-gray-700/50">
						{#each jobs as job (job.job_id ?? job.id)}
							<!-- A1: Row click opens drawer -->
							<tr
								class="hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition cursor-pointer"
								on:click={() => openDrawer(job)}
							>
								<td class="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400">{(job.job_id ?? job.id).slice(0, 8)}…</td>
								<td class="px-4 py-3 font-medium text-gray-800 dark:text-gray-200">{job.model_id ?? '—'}</td>
								<td class="px-4 py-3">
									<span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium {STATUS_COLORS[job.status] ?? ''}">
										{#if job.status === 'running'}<span class="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse inline-block" />{/if}
										{job.status}
									</span>
								</td>
								<td class="px-4 py-3 text-center text-gray-500 dark:text-gray-400">{job.attempt_count}/{job.max_attempts}</td>
								<td class="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">{formatTime(job.created_at)}</td>
								<td class="px-4 py-3 text-xs text-gray-400">{elapsed(job.created_at)}</td>
								<td class="px-4 py-3 text-right" on:click|stopPropagation>
									{#if job.status === 'queued' || job.status === 'running'}
										<button
											class="text-xs px-2 py-1 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition"
											on:click={() => handleCancel(job.job_id ?? job.id)}>{$i18n.t('Cancel')}</button>
									{:else if job.status === 'failed' || job.status === 'cancelled'}
										<!-- A3: Retry button in row -->
										<button
											class="text-xs px-2 py-1 rounded-lg text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition"
											on:click={async () => {
												const res = await retryJob($user?.token ?? '', job.job_id ?? job.id);
												if (res) { toast.success($i18n.t('Job re-queued')); await fetchJobs(); }
											}}>↻ {$i18n.t('Retry')}</button>
									{:else if job.status === 'completed'}
										<span class="text-green-500 text-xs">✓</span>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			{#if total > limit}
				<div class="flex items-center justify-between text-xs text-gray-400">
					<span>{skip + 1}–{Math.min(skip + limit, total)} of {total}</span>
					<div class="flex gap-2">
						<button class="px-3 py-1 rounded bg-gray-100 dark:bg-gray-800 disabled:opacity-40" disabled={skip === 0}
							on:click={async () => { skip = Math.max(0, skip - limit); await fetchJobs(); }}>← {$i18n.t('Prev')}</button>
						<button class="px-3 py-1 rounded bg-gray-100 dark:bg-gray-800 disabled:opacity-40" disabled={skip + limit >= total}
							on:click={async () => { skip += limit; await fetchJobs(); }}>{$i18n.t('Next')} →</button>
					</div>
				</div>
			{/if}
		{/if}

	<!-- ================================================================ -->
	<!-- ARCHIVE TAB                                                        -->
	<!-- ================================================================ -->
	{:else}
		<!-- Config banner -->
		{#if archiveConfig}
			<div class="flex flex-wrap gap-4 px-4 py-3 rounded-xl bg-gray-50 dark:bg-gray-800/60 text-xs text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700">
				<span>
					<span class="font-medium text-gray-700 dark:text-gray-300">{$i18n.t('Active retention')}:</span>
					{archiveConfig.job_retention_days}d
				</span>
				<span class="text-gray-300 dark:text-gray-600">|</span>
				<span>
					<span class="font-medium text-gray-700 dark:text-gray-300">{$i18n.t('Archive retention')}:</span>
					{archiveConfig.job_archive_retention_days === 0 ? '∞ ' + $i18n.t('(never purge)') : archiveConfig.job_archive_retention_days + 'd'}
				</span>
				<span class="text-gray-300 dark:text-gray-600">|</span>
				<span class="text-gray-400 dark:text-gray-500 italic">{$i18n.t('Set via JOB_RETENTION_DAYS / JOB_ARCHIVE_RETENTION_DAYS env vars')}</span>
			</div>
		{/if}

		<!-- Filters -->
		<div class="flex flex-wrap gap-2">
			<select
				class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 outline-none"
				bind:value={archiveStatusFilter}
				on:change={() => { archiveSkip = 0; fetchArchive(); }}
			>
				<option value="">{$i18n.t('All statuses')}</option>
				<option value="completed">completed</option>
				<option value="failed">failed</option>
				<option value="cancelled">cancelled</option>
			</select>
			<input
				class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 outline-none"
				placeholder={$i18n.t('Filter by model…')}
				bind:value={archiveModelFilter}
				on:input={() => { archiveSkip = 0; fetchArchive(); }}
			/>
		</div>

		{#if archiveLoading}
			<div class="space-y-2">
				{#each Array(4) as _}
					<div class="h-12 rounded-xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
				{/each}
			</div>
		{:else if archiveJobs.length === 0}
			<div class="flex flex-col items-center justify-center py-24 text-gray-400 dark:text-gray-600">
				<svg class="w-10 h-10 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
						d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
				</svg>
				<p class="text-sm">{$i18n.t('Archive is empty')}</p>
				<p class="text-xs mt-1">{$i18n.t('Terminal jobs older than the retention window are automatically archived')}</p>
			</div>
		{:else}
			<!-- Archive table: also clickable for drawer -->
			<div class="rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
				<table class="w-full text-sm">
					<thead>
						<tr class="bg-gray-50 dark:bg-gray-800/60 text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
							<th class="px-4 py-3 text-left font-medium">ID</th>
							<th class="px-4 py-3 text-left font-medium">{$i18n.t('Model')}</th>
							<th class="px-4 py-3 text-left font-medium">{$i18n.t('Status')}</th>
							<th class="px-4 py-3 text-left font-medium">{$i18n.t('Attempts')}</th>
							<th class="px-4 py-3 text-left font-medium">{$i18n.t('Created')}</th>
							<th class="px-4 py-3 text-left font-medium">{$i18n.t('Archived')}</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-gray-100 dark:divide-gray-700/50">
						{#each archiveJobs as job (job.id)}
							<tr
								class="hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition cursor-pointer"
								on:click={() => openDrawer({ ...job, job_id: job.id })}
							>
								<td class="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400">{job.id.slice(0, 8)}…</td>
								<td class="px-4 py-3 font-medium text-gray-800 dark:text-gray-200">{job.model_id ?? '—'}</td>
								<td class="px-4 py-3">
									<span class="px-2 py-0.5 rounded-full text-xs font-medium {STATUS_COLORS[job.status] ?? ''}">{job.status}</span>
								</td>
								<td class="px-4 py-3 text-center text-gray-500">{job.attempt_count}/{job.max_attempts}</td>
								<td class="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">{formatTime(job.created_at)}</td>
								<td class="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">{formatTime(job.archived_at)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			{#if archiveTotal > limit}
				<div class="flex items-center justify-between text-xs text-gray-400">
					<span>{archiveSkip + 1}–{Math.min(archiveSkip + limit, archiveTotal)} of {archiveTotal}</span>
					<div class="flex gap-2">
						<button class="px-3 py-1 rounded bg-gray-100 dark:bg-gray-800 disabled:opacity-40" disabled={archiveSkip === 0}
							on:click={async () => { archiveSkip = Math.max(0, archiveSkip - limit); await fetchArchive(); }}>← {$i18n.t('Prev')}</button>
						<button class="px-3 py-1 rounded bg-gray-100 dark:bg-gray-800 disabled:opacity-40" disabled={archiveSkip + limit >= archiveTotal}
							on:click={async () => { archiveSkip += limit; await fetchArchive(); }}>{$i18n.t('Next')} →</button>
					</div>
				</div>
			{/if}
		{/if}
	{/if}
</div>
