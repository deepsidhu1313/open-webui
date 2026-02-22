<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { user } from '$lib/stores';
	import { getJobAnalyticsExport } from '$lib/apis/jobs';

	const i18n = getContext('i18n');

	let stats: any = null;
	let loading = true;
	let error = false;
	let exporting = false;

	async function fetchAnalytics() {
		if (!$user?.token) return;
		try {
			const res = await fetch('/api/v1/jobs/analytics', {
				headers: { Authorization: `Bearer ${$user.token}` }
			});
			if (!res.ok) throw new Error(await res.text());
			stats = await res.json();
			error = false;
		} catch (e) {
			console.error(e);
			error = true;
		}
	}

	async function downloadCsv() {
		if (!$user?.token || exporting) return;
		exporting = true;
		try {
			const res = await getJobAnalyticsExport($user.token);
			if (!res || !res.ok) return;
			const blob = await res.blob();
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = 'job_analytics.csv';
			a.click();
			URL.revokeObjectURL(url);
		} finally {
			exporting = false;
		}
	}

	const STATUS_COLORS: Record<string, string> = {
		completed: 'bg-emerald-500',
		running: 'bg-blue-500',
		queued: 'bg-yellow-400',
		failed: 'bg-red-500',
		cancelled: 'bg-gray-400'
	};

	function pct(count: number, total: number) {
		return total > 0 ? Math.round((count / total) * 100) : 0;
	}

	// Daily history chart helpers
	function chartMax(history: any[]): number {
		return Math.max(1, ...history.map((d: any) => d.total));
	}
	function barHeight(value: number, maxVal: number): string {
		return `${Math.round((value / maxVal) * 100)}%`;
	}
	function shortDate(iso: string): string {
		const d = new Date(iso);
		return `${d.getMonth() + 1}/${d.getDate()}`;
	}

	onMount(async () => {
		await fetchAnalytics();
		loading = false;
	});
</script>

<div class="px-4 py-6 max-w-7xl mx-auto w-full space-y-8">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-xl font-semibold text-gray-800 dark:text-gray-100">{$i18n.t('Job Analytics')}</h2>
			<p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
				{$i18n.t('All-time aggregate stats across active + archived jobs')}
			</p>
		</div>
		<button
			class="text-xs px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition text-gray-700 dark:text-gray-300"
			on:click={fetchAnalytics}
		>↻ {$i18n.t('Refresh')}</button>
		<button
			class="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white transition disabled:opacity-60"
			disabled={exporting}
			on:click={downloadCsv}
		>⬇ {exporting ? $i18n.t('Exporting…') : $i18n.t('Export CSV')}</button>
	</div>

	{#if loading}
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
			{#each [1, 2, 3, 4] as _}
				<div class="h-24 rounded-2xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
			{/each}
		</div>
	{:else if error || !stats}
		<div class="flex flex-col items-center justify-center py-24 text-gray-400 dark:text-gray-600">
			<p class="text-sm">{$i18n.t('Could not load job analytics')}</p>
			<button class="mt-2 text-xs text-blue-500 hover:underline" on:click={fetchAnalytics}>
				{$i18n.t('Try again')}
			</button>
		</div>
	{:else}
		<!-- ================================================================ -->
		<!-- KPI Cards                                                          -->
		<!-- ================================================================ -->
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
			<div class="rounded-2xl p-5 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm">
				<p class="text-xs text-gray-400 dark:text-gray-500 mb-1">{$i18n.t('Total Jobs')}</p>
				<p class="text-2xl font-bold text-gray-800 dark:text-gray-100">{stats.total.toLocaleString()}</p>
				{#if stats.includes_archive}
					<p class="text-xs text-gray-400 mt-1">↳ {$i18n.t('includes archive')}</p>
				{/if}
			</div>
			<div class="rounded-2xl p-5 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm">
				<p class="text-xs text-gray-400 dark:text-gray-500 mb-1">{$i18n.t('Success Rate')}</p>
				<p class="text-2xl font-bold {stats.success_rate > 90 ? 'text-emerald-500' : stats.success_rate > 70 ? 'text-yellow-500' : 'text-red-500'}">
					{stats.success_rate}%
				</p>
			</div>
			<div class="rounded-2xl p-5 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm">
				<p class="text-xs text-gray-400 dark:text-gray-500 mb-1">{$i18n.t('Avg Wait Time')}</p>
				<p class="text-2xl font-bold text-gray-800 dark:text-gray-100">
					{#if stats.avg_wait_seconds < 60}
						{stats.avg_wait_seconds}s
					{:else}
						{Math.floor(stats.avg_wait_seconds / 60)}m {Math.round(stats.avg_wait_seconds % 60)}s
					{/if}
				</p>
			</div>
			<div class="rounded-2xl p-5 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm">
				<p class="text-xs text-gray-400 dark:text-gray-500 mb-1">{$i18n.t('Queued Now')}</p>
				<p class="text-2xl font-bold text-yellow-500">{stats.by_status?.queued ?? 0}</p>
			</div>
		</div>

		<!-- ================================================================ -->
		<!-- Status Breakdown Bar                                              -->
		<!-- ================================================================ -->
		{#if stats.total > 0}
			<section>
				<h3 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
					{$i18n.t('Status Breakdown')}
				</h3>
				<div class="rounded-2xl p-5 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm">
					<div class="flex h-4 rounded-full overflow-hidden gap-px mb-4">
						{#each Object.entries(stats.by_status) as [status, count]}
							{@const width = pct(count, stats.total)}
							{#if width > 0}
								<div
									class="{STATUS_COLORS[status] ?? 'bg-gray-300'} transition-all duration-700"
									style="width: {width}%"
									title="{status}: {count}"
								/>
							{/if}
						{/each}
					</div>
					<div class="flex flex-wrap gap-4">
						{#each Object.entries(stats.by_status) as [status, count]}
							<div class="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
								<span class="inline-block w-2.5 h-2.5 rounded-sm {STATUS_COLORS[status] ?? 'bg-gray-300'}" />
								<span class="capitalize">{status}</span>
								<span class="font-medium text-gray-800 dark:text-gray-200">({count})</span>
							</div>
						{/each}
					</div>
				</div>
			</section>
		{/if}

		<!-- ================================================================ -->
		<!-- Daily History Chart (last 90 days)                               -->
		<!-- ================================================================ -->
		{#if stats.daily_history?.length > 0}
			{@const maxVal = chartMax(stats.daily_history)}
			<section>
				<h3 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
					{$i18n.t('Daily Activity')} <span class="text-gray-400 normal-case font-normal">{$i18n.t('(last 90 days)')}</span>
				</h3>
				<div class="rounded-2xl p-5 bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 shadow-sm overflow-x-auto">
					<div class="flex items-end gap-0.5 min-w-max" style="height: 96px;">
						{#each stats.daily_history as day}
							<div class="flex flex-col items-center gap-0.5 group relative" style="width: max(8px, calc(100% / {stats.daily_history.length}))">
								<!-- Stacked bar: completed (green) + failed (red) -->
								<div class="w-full flex flex-col justify-end" style="height: 80px;">
									{#if day.total > 0}
										<div
											class="w-full bg-emerald-400 dark:bg-emerald-500 rounded-t-sm"
											style="height: {barHeight(day.completed, maxVal)}"
											title="{day.date}: {day.completed} completed"
										/>
										{#if day.failed > 0}
											<div
												class="w-full bg-red-400 dark:bg-red-500"
												style="height: {barHeight(day.failed, maxVal)}"
												title="{day.date}: {day.failed} failed"
											/>
										{/if}
									{:else}
										<div class="w-full bg-gray-100 dark:bg-gray-800 rounded-t-sm" style="height: 2px" />
									{/if}
								</div>
								<!-- Tooltip on hover -->
								<div class="absolute bottom-full mb-1 hidden group-hover:flex flex-col items-center z-10 pointer-events-none">
									<div class="bg-gray-800 text-white text-xs rounded px-2 py-1 whitespace-nowrap shadow-lg">
										{day.date}: {day.total} total · {day.completed} ✓ · {day.failed} ✗
									</div>
								</div>
							</div>
						{/each}
					</div>
					<!-- X-axis: show ~6 evenly spread date labels -->
					<div class="flex justify-between text-xs text-gray-400 mt-1 min-w-max">
						{#each stats.daily_history as day, i}
							{#if i === 0 || i === stats.daily_history.length - 1 || i % Math.max(1, Math.floor(stats.daily_history.length / 5)) === 0}
								<span>{shortDate(day.date)}</span>
							{/if}
						{/each}
					</div>
					<!-- Legend -->
					<div class="flex gap-4 mt-3 text-xs text-gray-500">
						<span class="flex items-center gap-1"><span class="inline-block w-2.5 h-2.5 rounded-sm bg-emerald-400" /> {$i18n.t('Completed')}</span>
						<span class="flex items-center gap-1"><span class="inline-block w-2.5 h-2.5 rounded-sm bg-red-400" /> {$i18n.t('Failed')}</span>
					</div>
				</div>
			</section>
		{/if}

		<!-- ================================================================ -->
		<!-- By Model Table                                                    -->
		<!-- ================================================================ -->
		{#if stats.by_model?.length > 0}
			<section>
				<h3 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
					{$i18n.t('Jobs by Model')}
				</h3>
				<div class="rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
					<table class="w-full text-sm">
						<thead>
							<tr class="bg-gray-50 dark:bg-gray-800/60 text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
								<th class="px-4 py-3 text-left font-medium">{$i18n.t('Model')}</th>
								<th class="px-4 py-3 text-right font-medium">{$i18n.t('Total')}</th>
								<th class="px-4 py-3 text-right font-medium">{$i18n.t('Completed')}</th>
								<th class="px-4 py-3 text-right font-medium">{$i18n.t('Failed')}</th>
								<th class="px-4 py-3 text-right font-medium">{$i18n.t('Success %')}</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-gray-100 dark:divide-gray-700/50">
							{#each stats.by_model as m}
								{@const modelSuccess = m.total > 0 ? Math.round((m.completed / m.total) * 100) : 0}
								<tr class="hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition">
									<td class="px-4 py-3 font-medium text-gray-800 dark:text-gray-200">{m.model_id}</td>
									<td class="px-4 py-3 text-right text-gray-500 dark:text-gray-400">{m.total}</td>
									<td class="px-4 py-3 text-right text-emerald-600 dark:text-emerald-400">{m.completed}</td>
									<td class="px-4 py-3 text-right text-red-500 dark:text-red-400">{m.failed}</td>
									<td class="px-4 py-3 text-right">
										<span class="{modelSuccess > 90 ? 'text-emerald-500' : modelSuccess > 70 ? 'text-yellow-500' : 'text-red-500'} font-medium">
											{modelSuccess}%
										</span>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{/if}

		<!-- ================================================================ -->
		<!-- By User Table (top 20)                                            -->
		<!-- ================================================================ -->
		{#if stats.by_user?.length > 0}
			<section>
				<h3 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
					{$i18n.t('Top Users by Job Count')}
				</h3>
				<div class="rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
					<table class="w-full text-sm">
						<thead>
							<tr class="bg-gray-50 dark:bg-gray-800/60 text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
								<th class="px-4 py-3 text-left font-medium">#</th>
								<th class="px-4 py-3 text-left font-medium">{$i18n.t('User ID')}</th>
								<th class="px-4 py-3 text-right font-medium">{$i18n.t('Total')}</th>
								<th class="px-4 py-3 text-right font-medium">{$i18n.t('Completed')}</th>
								<th class="px-4 py-3 text-right font-medium">{$i18n.t('Failed')}</th>
								<th class="px-4 py-3 text-right font-medium">{$i18n.t('Cancelled')}</th>
								<th class="px-4 py-3 text-right font-medium">{$i18n.t('Success %')}</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-gray-100 dark:divide-gray-700/50">
							{#each stats.by_user as u, idx}
								{@const userSuccess = u.total > 0 ? Math.round((u.completed / u.total) * 100) : 0}
								<tr class="hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition">
									<td class="px-4 py-3 text-xs text-gray-400">{idx + 1}</td>
									<td class="px-4 py-3 font-mono text-xs text-gray-600 dark:text-gray-300">{u.user_id.slice(0, 12)}…</td>
									<td class="px-4 py-3 text-right text-gray-500 dark:text-gray-400">{u.total}</td>
									<td class="px-4 py-3 text-right text-emerald-600 dark:text-emerald-400">{u.completed}</td>
									<td class="px-4 py-3 text-right text-red-500 dark:text-red-400">{u.failed}</td>
									<td class="px-4 py-3 text-right text-gray-400">{u.cancelled}</td>
									<td class="px-4 py-3 text-right">
										<span class="{userSuccess > 90 ? 'text-emerald-500' : userSuccess > 70 ? 'text-yellow-500' : 'text-red-500'} font-medium">
											{userSuccess}%
										</span>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{/if}
	{/if}
</div>
