<script lang="ts">
  let { tag = "section", id = "", children }: { tag?: string; id?: string; children?: import("svelte").Snippet } = $props();
</script>

<svelte:element this={tag} {id} class="py-16 px-6 max-w-6xl mx-auto relative">
  {@render children?.()}
</svelte:element>
