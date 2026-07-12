<script lang="ts">
  import "../app.css";
  import { PROJECT } from "$lib/data/meta";
  import { base } from "$app/paths";
  let { children } = $props();
</script>

<header class="fixed top-0 w-full z-50 backdrop-blur-sm bg-slate-950/80 border-b border-slate-800">
  <nav class="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
    <a href="{base}/" class="flex items-center gap-2 text-white font-semibold text-sm tracking-tight">
      <span class="text-emerald-500 font-mono text-xs">[EFH]</span>
      {PROJECT.name}
    </a>
    <div class="flex items-center gap-6 text-xs font-mono">
      <a href="{base}/#architecture" class="text-slate-500 hover:text-slate-300 transition-colors">Arch</a>
      <a href="{base}/#routing" class="text-slate-500 hover:text-slate-300 transition-colors">Routing</a>
      <a href="{base}/#smoke-test" class="text-slate-500 hover:text-slate-300 transition-colors">Smoke</a>
      <a href="{base}/#tiers" class="text-slate-500 hover:text-slate-300 transition-colors">Tiers</a>
    </div>
    <a href={PROJECT.repo} class="text-slate-500 hover:text-emerald-400 text-xs font-mono transition-colors" target="_blank" rel="noopener">
      GitHub ↗
    </a>
  </nav>
</header>

<main class="pt-14">
  {@render children?.()}
</main>

<footer class="border-t border-slate-800 py-8 text-center text-slate-600 text-xs font-mono">
  {PROJECT.name} · {PROJECT.version} · <a href={PROJECT.repo} class="hover:text-slate-400 transition-colors">{PROJECT.license} License</a>
</footer>
