<script lang="ts">
  import Section from "$lib/components/ui/Section.svelte";
  import { METRICS, PRINCIPLE, PROJECT, STATUS_LINE, STATUS_CAVEAT } from "$lib/data/meta";
  import { base } from "$app/paths";
</script>

<Section tag="header">
  <div class="space-y-6">
    <!-- Status line -->
    <div class="flex items-center gap-2 font-mono text-xs text-slate-500">
      <span class="inline-block w-2 h-2 rounded-full bg-emerald-500"></span>
      <span>{STATUS_LINE}</span>
    </div>

    <!-- Title -->
    <h1 class="text-[32px] leading-tight font-semibold tracking-[-0.02em] text-white">
      Evidence-First<br />Harness
    </h1>

    <!-- Subtitle -->
    <p class="text-slate-400 text-sm leading-relaxed max-w-xl">
      Deterministic assurance for AI-generated code.
      Treats every AI patch as an untrusted proposal —
      routes outputs through <a href="{PROJECT.repo}" class="text-emerald-400 hover:underline">deterministic policy gates</a> that produce evidence bundles.
    </p>

    <!-- Principle quote -->
    <blockquote class="border-l-2 border-emerald-500/40 pl-4 py-1 text-slate-500 text-xs font-mono italic max-w-lg">
      "{PRINCIPLE}"
    </blockquote>

    <!-- CTAs -->
    <div class="flex gap-3 pt-2">
      <a href="{base}/#smoke-test" class="inline-flex items-center gap-2 px-4 py-2 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono rounded-sm hover:bg-emerald-500/20 transition-colors">
        ▸ See Smoke Test
      </a>
      <a href={PROJECT.repo} target="_blank" rel="noopener" class="inline-flex items-center gap-2 px-4 py-2 border border-slate-700 text-slate-400 text-xs font-mono rounded-sm hover:border-slate-500 hover:text-slate-300 transition-colors">
        GitHub ↗
      </a>
    </div>

    <!-- Metrics row -->
    <div class="grid grid-cols-3 sm:grid-cols-6 gap-2 pt-8">
      {#each METRICS as m}
        <a href={m.source} target="_blank" rel="noopener" class="border border-slate-800 rounded-sm p-3 text-center hover:border-slate-600 transition-colors block no-underline">
          <div class="text-lg font-mono font-medium text-white">{m.label}</div>
          <div class="text-[10px] text-slate-500 font-mono mt-0.5">{m.desc}</div>
        </a>
      {/each}
    </div>
    <p class="text-slate-600 text-[10px] font-mono">{STATUS_CAVEAT}</p>
  </div>
</Section>
