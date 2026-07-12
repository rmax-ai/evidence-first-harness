<script lang="ts">
  import Section from "$lib/components/ui/Section.svelte";
  import { TIERS } from "$lib/data/meta";

  const TIER_COLORS: Record<string, { border: string; text: string; bg: string; badgeBg: string }> = {
    emerald: { border: "border-emerald-500/30", text: "text-emerald-400", bg: "bg-emerald-500/5", badgeBg: "bg-emerald-500/10" },
    amber: { border: "border-amber-500/30", text: "text-amber-400", bg: "bg-amber-500/5", badgeBg: "bg-amber-500/10" },
    red: { border: "border-red-500/30", text: "text-red-400", bg: "bg-red-500/5", badgeBg: "bg-red-500/10" },
  };
</script>

<Section id="tiers">
  <h2 class="text-[20px] leading-snug font-medium tracking-[-0.01em] text-white mb-8">
    Evidence Tiers
  </h2>

  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    {#each TIERS as tier}
      {@const c = TIER_COLORS[tier.color]}
      <div class="border {c.border} rounded-sm p-5 {c.bg}">
        <div class="flex items-center gap-2 mb-3">
          <span class="inline-flex items-center px-2 py-0.5 rounded-sm text-[10px] font-mono border {c.border} {c.text} {c.badgeBg}">
            Tier {tier.tier}
          </span>
          <span class="text-slate-600 text-[10px] font-mono">{tier.approval}</span>
        </div>
        <p class="text-slate-400 text-xs leading-relaxed font-mono">
          {tier.checks}
        </p>
      </div>
    {/each}
  </div>
</Section>
