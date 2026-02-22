<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import { user } from '$lib/stores';
	import { getServerStats } from '$lib/apis/system';

	const i18n = getContext('i18n');

	let stats: Record<string, any> = {};
	let loading = true;
	let pollInterval: ReturnType<typeof setInterval>;

	async function fetchStats() {
		if (!$user?.token) return;
		const s = await getServerStats($user.token);
		if (s) stats = s;
	}

	function gaugeColor(pct: number) {
		if (pct > 85) return 'bg-red-500';
		if (pct > 60) return 'bg-yellow-400';
		return 'bg-emerald-500';
	}

	function fmtMs(ms: number) {
		return `${ms?.toFixed(0) ?? '—'}ms`;
	}

	onMount(async () => {
		await fetchStats();
		loading = false;
		pollInterval = setInterval(fetchStats, 15_000);
	});
	onDestroy(() => clearInterval(pollInterval));
</script>

<div class="px-4 py-6 max-w-7xl mx-auto w-full space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-xl font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('Ollama Backends')}
			</h2>
			<p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
				{$i18n.t('Live health and performance per backend')} · {$i18n.t('Auto-refreshes every 15s')}
			</p>
		</div>
		<button
			class="text-xs px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition text-gray-700 dark:text-gray-300"
			on:click={fetchStats}
		>
			↻ {$i18n.t('Refresh')}
		</button>
	</div>

	{#if loading}
		<div class="space-y-4">
			{#each [1, 2] as _}
				<div class="h-40 rounded-2xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
			{/each}
		</div>
	{:else if Object.keys(stats).length === 0}
		<div class="flex flex-col items-center justify-center py-24 text-gray-400 dark:text-gray-600">
			<p class="text-sm">{$i18n.t('No Ollama backends found')}</p>
			<p class="text-xs mt-1">{$i18n.t('Enable Ollama API in Settings to see backend stats')}</p>
		</div>
	{:else}
		{#each Object.entries(stats) as [url, bStat]}
			{@const healthy = bStat.health_status === 'healthy'}
			<div class="rounded-2xl p-6 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm">
				<!-- URL + health -->
				<div class="flex items-center gap-3 mb-5">
					<div class="relative flex-shrink-0">
						<span
							class="inline-block w-3 h-3 rounded-full {healthy ? 'bg-emerald-500' : 'bg-red-500'}"
						/>
						{#if healthy}
							<span class="absolute inset-0 rounded-full bg-emerald-500 animate-ping opacity-50" />
						{/if}
					</div>
					<span class="font-mono text-sm font-medium text-gray-800 dark:text-gray-200 truncate">{url}</span>
					<span class="ml-auto text-xs px-2 py-0.5 rounded-full {healthy ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400'}">
						{bStat.health_status ?? 'unknown'}
					</span>
				</div>

				<!-- Stats grid -->
				<div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
					<div class="text-center">
						<p class="text-2xl font-bold text-gray-800 dark:text-gray-100">{bStat.active_jobs ?? 0}</p>
						<p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{$i18n.t('Active Jobs')}</p>
					</div>
					<div class="text-center">
						<p class="text-2xl font-bold text-gray-800 dark:text-gray-100">{fmtMs(bStat.avg_response_time_ms)}</p>
						<p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{$i18n.t('Avg Response')}</p>
					</div>
					<div class="text-center">
						<p class="text-2xl font-bold text-gray-800 dark:text-gray-100">
							{bStat.avg_tokens_per_second?.toFixed(1) ?? '—'}
						</p>
						<p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{$i18n.t('tok/s')}</p>
					</div>
					<div class="text-center">
						<p class="text-2xl font-bold text-gray-800 dark:text-gray-100">{bStat.total_requests ?? 0}</p>
						<p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{$i18n.t('Total Requests')}</p>
					</div>
				</div>

				<!-- Response-time gauge -->
				{#if bStat.avg_response_time_ms !== undefined}
					{@const pctFill = Math.min(100, (bStat.avg_response_time_ms / 30000) * 100)}
					<div>
						<div class="flex justify-between text-xs text-gray-400 mb-1">
							<span>{$i18n.t('Response time load')}</span>
							<span>{fmtMs(bStat.avg_response_time_ms)} / 30s target</span>
						</div>
						<div class="h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
							<div
								class="h-full rounded-full transition-all duration-700 {gaugeColor(pctFill)}"
								style="width: {pctFill}%"
							/>
						</div>
					</div>
				{/if}
			</div>
		{/each}
	{/if}
</div>
