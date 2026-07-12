<script lang="ts">
  import Section from "$lib/components/ui/Section.svelte";
  import { QUICK_START, SMOKE_OUTPUT } from "$lib/data/meta";
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
      <h3 class="text-[16px] leading-normal font-medium text-slate-300 mb-3 font-mono">[ Terminal Output ]</h3>
      <div class="border border-slate-800 rounded-sm overflow-hidden">
        <div class="flex items-center justify-between px-3 py-1.5 bg-slate-900/60 border-b border-slate-800">
          <span class="text-slate-500 font-mono text-[10px]">sharn@evidence-harness:~</span>
          <span class="text-slate-600 font-mono text-[10px]">93.4s</span>
        </div>
        <div class="relative bg-[#020617] border-l-2 border-emerald-500/60">
          <pre class="text-slate-400 font-mono text-[11px] leading-relaxed p-3 overflow-x-auto"><code>{SMOKE_OUTPUT}</code></pre>
          <span class="absolute bottom-3 left-7 inline-block w-[7px] h-[15px] bg-emerald-500/80 animate-pulse"></span>
        </div>
      </div>
    </div>
  </div>
</Section>
