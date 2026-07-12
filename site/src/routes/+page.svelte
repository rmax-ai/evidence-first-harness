<script lang="ts">
  import Hero from "$lib/components/sections/Hero.svelte";
  import Architecture from "$lib/components/sections/Architecture.svelte";
  import ModelRouting from "$lib/components/sections/ModelRouting.svelte";
  import SmokeTest from "$lib/components/sections/SmokeTest.svelte";
  import EvidenceTiers from "$lib/components/sections/EvidenceTiers.svelte";
</script>

<Hero />

<!-- Container grid guide lines -->
<div class="fixed top-0 left-[calc(50%-576px)] w-[1px] h-full border-l border-dotted border-slate-800/30 pointer-events-none z-0 hidden lg:block"></div>
<div class="fixed top-0 right-[calc(50%-576px)] w-[1px] h-full border-r border-dotted border-slate-800/30 pointer-events-none z-0 hidden lg:block"></div>

<SmokeTest />
<Architecture />
<ModelRouting />
<EvidenceTiers />
