<script lang="ts">
  import Section from "$lib/components/ui/Section.svelte";
  import { QUICK_START, SMOKE_OUTPUT, SMOKE_CAVEAT, COST_BREAKDOWN, PRICING_SOURCES } from "$lib/data/meta";
</script>

<Section id="smoke-test">
  <h2 class="text-[20px] leading-snug font-medium tracking-[-0.01em] text-white mb-8">
    Smoke Test
  </h2>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <!-- Quick Start -->
    <div>
      <h3 class="text-[16px] leading-normal font-medium text-slate-300 mb-3 font-mono">[ Quick Start ]</h3>
      <div class="space-y-2">
        {#each QUICK_START as step, i}
          <div class="group border border-slate-800 rounded-sm overflow-hidden">
            <div class="flex items-center gap-3 px-3 py-2 bg-slate-900/60 border-b border-slate-800">
              <span class="text-slate-600 font-mono text-[10px] w-4">{String(i + 1).padStart(2, "0")}</span>
              <span class="text-slate-500 font-mono text-[10px] flex-1">{step.desc}</span>
            </div>
            <div class="px-3 py-2 bg-[#020617]">
              <code class="text-emerald-400 font-mono text-xs">{step.cmd}</code>
            </div>
          </div>
        {/each}
      </div>
    </div>

    <!-- Terminal output -->
    <div>
      <h3 class="text-[16px] leading-normal font-medium text-slate-300 mb-3 font-mono">[ Representative Run ]</h3>
      <div class="border border-slate-800 rounded-sm overflow-hidden">
        <div class="flex items-center justify-between px-3 py-1.5 bg-slate-900/60 border-b border-slate-800">
          <span class="text-slate-500 font-mono text-[10px]">sharn@evidence-harness:~</span>
          <span class="text-slate-600 font-mono text-[10px]">~90s</span>
        </div>
        <div class="relative bg-[#020617] border-l-2 border-emerald-500/60">
          <pre class="text-slate-400 font-mono text-[11px] leading-relaxed p-3 overflow-x-auto"><code>{SMOKE_OUTPUT}</code></pre>
          <span class="absolute bottom-3 left-7 inline-block w-[7px] h-[15px] bg-emerald-500/80 animate-pulse"></span>
        </div>
      </div>

      <!-- Caveat -->
      <div class="mt-4 p-3 border border-slate-800 rounded-sm bg-slate-900/40">
        <p class="text-slate-500 text-[10px] font-mono leading-relaxed">
          {SMOKE_CAVEAT}
        </p>
      </div>

      <!-- Cost breakdown -->
      <div class="mt-3 p-3 border border-slate-800 rounded-sm bg-slate-900/40">
        <p class="text-slate-500 text-[10px] font-mono leading-relaxed">
          {COST_BREAKDOWN}
        </p>
      </div>

      <!-- Source links -->
      <div class="mt-3 text-[10px] font-mono text-slate-600 space-x-4">
        <span>Pricing sources:</span>
        <a href={PRICING_SOURCES.anthropic} target="_blank" rel="noopener" class="text-slate-500 hover:text-slate-400">Anthropic</a>
        <a href={PRICING_SOURCES.anthropic_sonnet5} target="_blank" rel="noopener" class="text-slate-500 hover:text-slate-400">Sonnet 5</a>
        <a href={PRICING_SOURCES.openai} target="_blank" rel="noopener" class="text-slate-500 hover:text-slate-400">OpenAI</a>
        <a href={PRICING_SOURCES.gemini} target="_blank" rel="noopener" class="text-slate-500 hover:text-slate-400">Gemini</a>
      </div>
    </div>
  </div>
</Section>
