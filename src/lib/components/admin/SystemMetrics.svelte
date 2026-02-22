<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import { user } from '$lib/stores';
	import { getSystemMetrics, getServerStats } from '$lib/apis/system';
	import BackendHistoryChart from './BackendHistoryChart.svelte';

	const i18n = getContext('i18n');

	let metrics: any = null;
	let serverStats: any = {};
	let loading = true;
	let pollInterval: ReturnType<typeof setInterval>;

	async function fetchAll() {
		if (!$user?.token) return;
		const [m, s] = await Promise.all([
			getSystemMetrics($user.token),
			getServerStats($user.token)
		]);
		if (m) metrics = m;
		if (s) serverStats = s;
	}

	function gauge(pct: number) {
		// Returns a CSS width class for the gauge fill
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
				{$i18n.t('Live server and backend telemetry')} · {$i18n.t('Auto-refreshes every 10s')}
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

		<!-- ── Ollama Backends ── -->
		{#if Object.keys(metrics.ollama_backends ?? {}).length > 0}
			<section>
				<h3 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
					{$i18n.t('Ollama Backends')}
				</h3>
				<div class="space-y-4">
					{#each Object.entries(metrics.ollama_backends) as [url, bData]}
						{@const stat = serverStats[url] ?? {}}
						<div class="rounded-2xl p-5 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm">
							<!-- URL + health dot -->
							<div class="flex items-center gap-2 mb-4">
								<span
									class="inline-block w-2 h-2 rounded-full flex-shrink-0 {stat.health_status === 'healthy' ? 'bg-emerald-500' : stat.health_status ? 'bg-red-500' : 'bg-gray-400'}"
								/>
								<span class="font-mono text-sm text-gray-700 dark:text-gray-300 truncate">{url}</span>
							</div>

							<!-- Stat pills -->
							<div class="flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
								{#if stat.active_jobs !== undefined}
									<div class="flex items-center gap-1">
										<span class="font-medium text-gray-700 dark:text-gray-200">{stat.active_jobs}</span>
										<span>{$i18n.t('active jobs')}</span>
									</div>
								{/if}
								{#if stat.avg_response_time_ms !== undefined}
									<div class="flex items-center gap-1">
										<span class="font-medium text-gray-700 dark:text-gray-200">{stat.avg_response_time_ms?.toFixed(0)}ms</span>
										<span>{$i18n.t('avg response')}</span>
									</div>
								{/if}
								{#if stat.avg_tokens_per_second !== undefined}
									<div class="flex items-center gap-1">
										<span class="font-medium text-gray-700 dark:text-gray-200">{stat.avg_tokens_per_second?.toFixed(1)}</span>
										<span>{$i18n.t('tok/s')}</span>
									</div>
								{/if}
							</div>

							<!-- Loaded models from /api/ps -->
							{#if bData?.api_ps?.models?.length}
								<div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
									<p class="text-xs font-medium text-gray-400 dark:text-gray-500 mb-2">
										{$i18n.t('Loaded models')}
									</p>
									<div class="flex flex-wrap gap-2">
										{#each bData.api_ps.models as m}
											<div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-50 dark:bg-gray-800 text-xs">
												<span class="font-medium text-gray-700 dark:text-gray-300">{m.name ?? m.model}</span>
												{#if m.size_vram !== undefined}
													<span class="text-gray-400">{(m.size_vram / 1_073_741_824).toFixed(1)}GB VRAM</span>
												{/if}
											</div>
										{/each}
									</div>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			</section>
		{/if}
		<!-- B2: Backend History Charts -->
		<section class="mt-2">
			<BackendHistoryChart />
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
