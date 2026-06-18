<script lang="ts">
  import MoreGridSmall from "@iconify-svelte/ci/more-grid-small";

  import type { TagGroupInfo } from "./types";
  import TagsPanel from "./TagsPanel.svelte";
  import TagPill from "./TagPill.svelte";

  interface Props {
    tagGroup: TagGroupInfo;
  };

  let { tagGroup }: Props = $props();

  let groupPresent = $derived(tagGroup.tags.map(t => t.present).reduce((a, b) => a && b, true));
</script>


<div class="flex flex-row flex-wrap items-center gap-2 p-2 border border-gray-300 bg-gray-50 rounded-lg">
  <button
    class={[
      "text-sm h-6 w-6 rounded-sm tag-btn",
      groupPresent ? "tag-btn--on" : "tag-btn--off",
    ]}
    aria-label="Toggle group"
    // TODO: onclick
  >
    {#if tagGroup.hotkey}
      <span class="m-auto text-center font-medium">{tagGroup.hotkey}</span>
    {:else}
      <MoreGridSmall width="1em" height="1em" class="m-auto align-middle" />
    {/if}
  </button>
  
  {#each tagGroup.tags as tag}
    <TagPill tag={tag} />
  {/each}
</div>

{#if tagGroup.subgroups.length > 0}
  <div class="ml-8">
    <TagsPanel tagGroups={tagGroup.subgroups} />
  </div>
{/if}
