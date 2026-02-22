<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import { user } from '$lib/stores';

	const i18n = getContext('i18n');

	// Props
	export let autoRefreshMs: number = 60_000; // poll every 60 s

	// State
	let data: Record<string, Snapshot[]> = {};
	let backends: string[] = [];
	let selectedBackend = '';
	let loading = true;
	let error = false;
	let interval: ReturnType<typeof setInterval>;

	interface Snapshot {
		id: number;
		captured_at: number;
		backend_url: string;
		cpu_percent: number | null;
		ram_percent: number | null;
		active_jobs: number | null;
		queued_jobs: number | null;
		loaded_models: number | null;
		vram_used_gb: number | null;
		avg_tokens_per_second: number | null;
	}

	async function fetchSnapshots() {
		if (!$user?.token) return;
		try {
			const params = new URLSearchParams({ limit: '72' }); // ~6 h of 5-min snapshots
			if (selectedBackend) params.set('backend_url', selectedBackend);
			const res = await fetch(`/api/v1/system/snapshots?${params}`, {
				headers: { Authorization: `Bearer ${$user.token}` }
			});
			if (!res.ok) throw new Error(await res.text());
			const json = await res.json();
			data = json.backends ?? {};
			backends = Object.keys(data);
			if (!selectedBackend && backends.length > 0) selectedBackend = backends[0];
			error = false;
		} catch (e) {
			console.error(e);
			error = true;
		} finally {
			loading = false;
		}
	}

	// Convert snapshot array for a specific metric to chart points {label, value}
	function series(snaps: Snapshot[], key: keyof Snapshot) {
		return snaps.map((s) => ({
			label: new Date(s.captured_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
			value: s[key] as number | null
		}));
	}

	// Simple SVG line chart helper
	function svgPath(points: { value: number | null }[], w: number, h: number, max: number): string {
		const filled = points.map((p) => (p.value ?? 0));
		const step = w / Math.max(filled.length - 1, 1);
		return filled
			.map((v, i) => `${i === 0 ? 'M' : 'L'} ${i * step} ${h - (v / (max || 1)) * h}`)
			.join(' ');
	}

	function chartMax(snaps: { value: number | null }[]): number {
		const vals = snaps.map((s) => s.value ?? 0);
		return Math.max(1, ...vals);
	}

	onMount(() => {
		fetchSnapshots();
		interval = setInterval(fetchSnapshots, autoRefreshMs);
	});
	onDestroy(() => clearInterval(interval));

	$: activeSnaps = selectedBackend ? (data[selectedBackend] ?? []) : [];
	$: cpuSeries = series(activeSnaps, 'cpu_percent');
	$: ramSeries = series(activeSnaps, 'ram_percent');
	$: activeJobsSeries = series(activeSnaps, 'active_jobs');
	$: queuedJobsSeries = series(activeSnaps, 'queued_jobs');
	$: vramSeries = series(activeSnaps, 'vram_used_gb');
	$: jobMax = chartMax([...activeJobsSeries, ...queuedJobsSeries]);
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h3 class="text-base font-semibold text-gray-700 dark:text-gray-200">{$i18n.t('Backend History')}</h3>
			<p class="text-xs text-gray-400 mt-0.5">{$i18n.t('Last 6h • 5-min intervals')}</p>
		</div>
		<div class="flex items-center gap-2">
			{#if backends.length > 1}
				<select
					class="text-xs px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 outline-none"
					bind:value={selectedBackend}
					on:change={fetchSnapshots}
				>
					{#each backends as url}
						<option value={url}>{url}</option>
					{/each}
				</select>
			{/if}
			<button
				class="text-xs px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition"
				on:click={fetchSnapshots}
			>↻ {$i18n.t('Refresh')}</button>
		</div>
	</div>

	{#if loading}
		<div class="space-y-4">
			{#each [1, 2] as _}
				<div class="h-28 rounded-2xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
			{/each}
		</div>
	{:else if error}
		<div class="text-center py-16 text-gray-400 text-sm">
			{$i18n.t('Could not load snapshots — is the scheduler running?')}
		</div>
	{:else if activeSnaps.length === 0}
		<div class="text-center py-16 text-gray-400 text-sm space-y-1">
			<p>{$i18n.t('No snapshot data yet.')}</p>
			<p class="text-xs">{$i18n.t('The scheduler collects a snapshot every 5 minutes.')}</p>
		</div>
	{:else}
		<!-- Grid of metric mini-charts -->
		<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">

			<!-- CPU -->
			<div class="rounded-2xl bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 p-4 shadow-sm">
				<div class="flex justify-between text-xs text-gray-400 mb-2">
					<span class="font-medium text-gray-600 dark:text-gray-300">{$i18n.t('CPU %')}</span>
					<span>{(activeSnaps.at(-1)?.cpu_percent ?? 0).toFixed(1)}%</span>
				</div>
				<svg viewBox="0 0 240 60" class="w-full h-16" preserveAspectRatio="none">
					<path
						d={svgPath(cpuSeries, 240, 60, 100)}
						fill="none" stroke="#6366f1" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
					/>
				</svg>
				<div class="flex justify-between text-[10px] text-gray-300 dark:text-gray-600 mt-1">
					<span>{cpuSeries.at(0)?.label ?? ''}</span>
					<span>{cpuSeries.at(-1)?.label ?? ''}</span>
				</div>
			</div>

			<!-- RAM -->
			<div class="rounded-2xl bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 p-4 shadow-sm">
				<div class="flex justify-between text-xs text-gray-400 mb-2">
					<span class="font-medium text-gray-600 dark:text-gray-300">{$i18n.t('RAM %')}</span>
					<span>{(activeSnaps.at(-1)?.ram_percent ?? 0).toFixed(1)}%</span>
				</div>
				<svg viewBox="0 0 240 60" class="w-full h-16" preserveAspectRatio="none">
					<path
						d={svgPath(ramSeries, 240, 60, 100)}
						fill="none" stroke="#10b981" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
					/>
				</svg>
				<div class="flex justify-between text-[10px] text-gray-300 dark:text-gray-600 mt-1">
					<span>{ramSeries.at(0)?.label ?? ''}</span>
					<span>{ramSeries.at(-1)?.label ?? ''}</span>
				</div>
			</div>

			<!-- Active + Queued jobs -->
			<div class="rounded-2xl bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 p-4 shadow-sm">
				<div class="flex justify-between text-xs text-gray-400 mb-2">
					<span class="font-medium text-gray-600 dark:text-gray-300">{$i18n.t('Jobs (active / queued)')}</span>
					<span>
						{activeSnaps.at(-1)?.active_jobs ?? 0} /
						{activeSnaps.at(-1)?.queued_jobs ?? 0}
					</span>
				</div>
				<svg viewBox="0 0 240 60" class="w-full h-16" preserveAspectRatio="none">
					<path d={svgPath(activeJobsSeries, 240, 60, jobMax)} fill="none" stroke="#3b82f6" stroke-width="1.5" />
					<path d={svgPath(queuedJobsSeries, 240, 60, jobMax)} fill="none" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4 2" />
				</svg>
				<div class="flex items-center gap-3 mt-1 text-[10px] text-gray-400">
					<span class="flex items-center gap-1"><span class="inline-block w-3 h-0.5 bg-blue-500 rounded" /> {$i18n.t('running')}</span>
					<span class="flex items-center gap-1"><span class="inline-block w-3 h-0.5 bg-yellow-400 rounded border-dashed" /> {$i18n.t('queued')}</span>
				</div>
			</div>

			<!-- VRAM -->
			{#if vramSeries.some((p) => p.value !== null && p.value > 0)}
				<div class="rounded-2xl bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 p-4 shadow-sm">
					<div class="flex justify-between text-xs text-gray-400 mb-2">
						<span class="font-medium text-gray-600 dark:text-gray-300">{$i18n.t('VRAM (GB)')}</span>
						<span>{(activeSnaps.at(-1)?.vram_used_gb ?? 0).toFixed(2)} GB</span>
					</div>
					<svg viewBox="0 0 240 60" class="w-full h-16" preserveAspectRatio="none">
						<path
							d={svgPath(vramSeries, 240, 60, chartMax(vramSeries))}
							fill="none" stroke="#ec4899" stroke-width="1.5" stroke-linecap="round"
						/>
					</svg>
					<div class="flex items-center gap-1 mt-1 text-[10px] text-gray-300 dark:text-gray-600">
						<span>{activeSnaps.at(-1)?.loaded_models ?? 0} {$i18n.t('loaded model(s)')}</span>
					</div>
				</div>
			{/if}

		</div>
	{/if}
</div>
