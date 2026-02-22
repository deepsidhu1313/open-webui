<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import { user } from '$lib/stores';
	import { getSystemMetrics } from '$lib/apis/system';

	const i18n = getContext('i18n');

	let metrics: any = null;
	let loading = true;
	let pollInterval: ReturnType<typeof setInterval>;

	async function fetchAll() {
		if (!$user?.token) return;
		const m = await getSystemMetrics($user.token);
		if (m) metrics = m;
	}

	function gauge(pct: number) {
		return `${Math.min(100, Math.max(0, pct))}%`;
	}

	function gaugeColor(pct: number) {
		if (pct > 85) return 'bg-red-500';
		if (pct > 65) return 'bg-yellow-500';
		return 'bg-emerald-500';
	}

	function fmtGb(gb: number) {
		return `${gb?.toFixed(1)} GB`;
	}

	onMount(async () => {
		await fetchAll();
		loading = false;
		pollInterval = setInterval(fetchAll, 10_000);
	});

	onDestroy(() => clearInterval(pollInterval));
</script>

<div class="px-4 py-6 max-w-7xl mx-auto w-full space-y-8">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-xl font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('System Metrics')}
			</h2>
			<p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
				{$i18n.t('Open WebUI server health')} · {$i18n.t('Auto-refreshes every 10s')}
			</p>
		</div>
		<button
			class="text-xs px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition text-gray-700 dark:text-gray-300"
			on:click={fetchAll}
		>
			↻ {$i18n.t('Refresh')}
		</button>
	</div>

	{#if loading}
		<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
			{#each [1, 2, 3] as _}
				<div class="h-28 rounded-2xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
			{/each}
		</div>
	{:else if metrics}
		<!-- ── Open WebUI server gauges ── -->
		<section>
			<h3 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
				{$i18n.t('Open WebUI Server')}
			</h3>
			<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
				<!-- CPU -->
				<div class="rounded-2xl p-5 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm">
					<div class="flex items-center justify-between mb-3">
						<span class="text-sm font-medium text-gray-600 dark:text-gray-400">CPU</span>
						<span class="text-lg font-bold text-gray-800 dark:text-gray-100">
							{metrics.server.cpu_percent}%
						</span>
					</div>
					<div class="h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
						<div
							class="h-full rounded-full transition-all duration-700 {gaugeColor(metrics.server.cpu_percent)}"
							style="width: {gauge(metrics.server.cpu_percent)}"
						/>
					</div>
				</div>

				<!-- RAM -->
				<div class="rounded-2xl p-5 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm">
					<div class="flex items-center justify-between mb-3">
						<span class="text-sm font-medium text-gray-600 dark:text-gray-400">RAM</span>
						<span class="text-lg font-bold text-gray-800 dark:text-gray-100">
							{metrics.server.ram_percent}%
						</span>
					</div>
					<div class="h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
						<div
							class="h-full rounded-full transition-all duration-700 {gaugeColor(metrics.server.ram_percent)}"
							style="width: {gauge(metrics.server.ram_percent)}"
						/>
					</div>
					<p class="text-xs text-gray-400 dark:text-gray-500 mt-2">
						{fmtGb(metrics.server.ram_used_gb)} / {fmtGb(metrics.server.ram_total_gb)}
					</p>
				</div>

				<!-- Disk -->
				<div class="rounded-2xl p-5 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm">
					<div class="flex items-center justify-between mb-3">
						<span class="text-sm font-medium text-gray-600 dark:text-gray-400">{$i18n.t('Disk')}</span>
						<span class="text-lg font-bold text-gray-800 dark:text-gray-100">
							{metrics.server.disk_percent}%
						</span>
					</div>
					<div class="h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
						<div
							class="h-full rounded-full transition-all duration-700 {gaugeColor(metrics.server.disk_percent)}"
							style="width: {gauge(metrics.server.disk_percent)}"
						/>
					</div>
					<p class="text-xs text-gray-400 dark:text-gray-500 mt-2">
						{fmtGb(metrics.server.disk_used_gb)} / {fmtGb(metrics.server.disk_total_gb)}
					</p>
				</div>
			</div>
		</section>

	{:else}
		<div class="flex flex-col items-center justify-center py-24 text-gray-400 dark:text-gray-600">
			<p class="text-sm">{$i18n.t('Could not load system metrics')}</p>
			<button class="mt-2 text-xs text-blue-500 hover:underline" on:click={fetchAll}>
				{$i18n.t('Try again')}
			</button>
		</div>
	{/if}
</div>

