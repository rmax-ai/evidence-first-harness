<script lang="ts">
  import Section from "$lib/components/ui/Section.svelte";
  import { BOUNDARY } from "$lib/data/meta";
  import { base } from "$app/paths";
</script>

<Section id="architecture">
  <h2 class="text-[20px] leading-snug font-medium tracking-[-0.01em] text-white mb-8">
    Architecture
  </h2>

  <p class="text-slate-500 text-xs font-mono mb-4">
    Illustrative architecture — not a benchmark or production deployment.
    In the shown configuration, LLM agents produce implementation and review artifacts;
    deterministic checks and policy decide the workflow outcome.
  </p>

  <!-- Pipeline Diagram -->
  <div class="mb-12 border border-slate-800 rounded-sm overflow-hidden">
    <div class="flex items-center justify-between px-3 py-1.5 bg-slate-900/60 border-b border-slate-800">
      <span class="text-slate-500 font-mono text-[10px]">pipeline.svg</span>
      <span class="text-slate-600 font-mono text-[10px]">17 nodes</span>
    </div>
    <img src="{base}/pipeline.svg" alt="Evidence-First Harness Pipeline — 17-node workflow" class="w-full h-auto" />
  </div>

  <!-- Boundary Table -->
  <div class="overflow-x-auto">
    <table class="w-full border border-slate-800 rounded-none font-mono text-xs">
      <thead>
        <tr class="bg-slate-900/60 border-b border-slate-800">
          <th class="text-left px-3 py-2 text-slate-500 font-normal w-8">#</th>
          <th class="text-left px-3 py-2 text-slate-500 font-normal">Component</th>
          <th class="text-left px-3 py-2 text-slate-500 font-normal">Type</th>
          <th class="text-left px-3 py-2 text-slate-500 font-normal">Controls</th>
        </tr>
      </thead>
      <tbody>
        {#each BOUNDARY as row, i}
          <tr class="border-b border-slate-800/50 {i % 2 === 1 ? 'bg-slate-900/20' : ''} hover:bg-slate-900/40 transition-colors">
            <td class="px-3 py-2 text-slate-600 text-[10px]">[{String(i + 1).padStart(2, "0")}]</td>
            <td class="px-3 py-2 text-slate-300">{row.component}</td>
            <td class="px-3 py-2">
              <span class="inline-flex items-center px-2 py-0.5 rounded-sm text-[10px] border
                {row.type === 'deterministic'
                  ? 'border-emerald-500/40 text-emerald-400 bg-emerald-500/5'
                  : 'border-amber-500/40 text-amber-400 bg-amber-500/5'}">
                {row.type === 'deterministic' ? 'DETERMINISTIC' : 'LLM AGENT'}
              </span>
            </td>
            <td class="px-3 py-2 text-slate-500">{row.controls}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</Section>
