<script lang="ts">
  import Section from "$lib/components/ui/Section.svelte";
  import { AGENT_ROUTING, AGENT_FOOTNOTE, PRICING, PRICING_SOURCES } from "$lib/data/meta";
</script>

<Section id="routing">
  <h2 class="text-[20px] leading-snug font-medium tracking-[-0.01em] text-white mb-8">
    Model Routing &amp; Pricing
  </h2>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <!-- Agent Routing -->
    <div>
      <h3 class="text-[16px] leading-normal font-medium text-slate-300 mb-3 font-mono">[ Agent Routing ]</h3>
      <div class="overflow-x-auto">
        <table class="w-full border border-slate-800 rounded-none font-mono text-xs">
          <thead>
            <tr class="bg-slate-900/60 border-b border-slate-800">
              <th class="text-left px-3 py-2 text-slate-500 font-normal">Agent</th>
              <th class="text-left px-3 py-2 text-slate-500 font-normal">Model</th>
              <th class="text-left px-3 py-2 text-slate-500 font-normal">Provider</th>
              <th class="text-center px-3 py-2 text-slate-500 font-normal w-12">Live</th>
              <th class="text-right px-3 py-2 text-slate-500 font-normal w-12">In</th>
              <th class="text-right px-3 py-2 text-slate-500 font-normal w-12">Out</th>
            </tr>
          </thead>
          <tbody>
            {#each AGENT_ROUTING as row, i}
              <tr class="border-b border-slate-800/50 {i % 2 === 1 ? 'bg-slate-900/20' : ''}">
                <td class="px-3 py-2 text-slate-300">{row.agent}</td>
                <td class="px-3 py-2 text-slate-400">{row.model}</td>
                <td class="px-3 py-2 text-slate-400">{row.provider}</td>
                <td class="px-3 py-2 text-center">
                  {#if row.live}
                    <span class="inline-block w-2 h-2 rounded-full bg-emerald-500" title="Live"></span>
                  {:else}
                    <span class="inline-block w-2 h-2 rounded-full bg-slate-600" title="Stub"></span>
                  {/if}
                </td>
                <td class="px-3 py-2 text-right text-slate-500">{row.inTokens}</td>
                <td class="px-3 py-2 text-right text-slate-500">{row.outTokens}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="mt-2 text-slate-600 text-[10px] font-mono">{AGENT_FOOTNOTE}</p>
    </div>

    <!-- Pricing -->
    <div>
      <h3 class="text-[16px] leading-normal font-medium text-slate-300 mb-3 font-mono">[ Pricing — USD per 1M tokens, as of 2026-07-14 ]</h3>
      <div class="overflow-x-auto">
        <table class="w-full border border-slate-800 rounded-none font-mono text-xs">
          <thead>
            <tr class="bg-slate-900/60 border-b border-slate-800">
              <th class="text-left px-3 py-2 text-slate-500 font-normal">Model</th>
              <th class="text-right px-3 py-2 text-slate-500 font-normal w-20">Input $</th>
              <th class="text-right px-3 py-2 text-slate-500 font-normal w-20">Output $</th>
            </tr>
          </thead>
          <tbody>
            {#each PRICING as row, i}
              <tr class="border-b border-slate-800/50 {i % 2 === 1 ? 'bg-slate-900/20' : ''}">
                <td class="px-3 py-2 text-slate-300">
                  {#if row.source}
                    <a href={row.source} target="_blank" rel="noopener" class="hover:text-emerald-400 transition-colors">{row.model}</a>
                  {:else}
                    {row.model}
                  {/if}
                </td>
                <td class="px-3 py-2 text-right text-slate-400">${row.inputPrice.toFixed(2)}</td>
                <td class="px-3 py-2 text-right text-slate-400">${row.outputPrice.toFixed(2)}</td>
              </tr>
              {#if row.note}
                <tr class="{i % 2 === 1 ? 'bg-slate-900/20' : ''}">
                  <td colspan="3" class="px-3 py-1 text-slate-600 text-[9px] font-mono">{row.note}</td>
                </tr>
              {/if}
            {/each}
          </tbody>
        </table>
      </div>

      <!-- Independence note -->
      <p class="mt-4 text-slate-600 text-[10px] font-mono leading-relaxed">
        The harness routes implementation and evaluation through distinct roles.
        In this alpha, 3 of 6 agent roles are live LLM agents and the remaining
        evaluator roles are stubbed or deterministic placeholders.
      </p>
    </div>
  </div>
</Section>
