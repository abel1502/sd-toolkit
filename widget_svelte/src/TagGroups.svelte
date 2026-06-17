<script lang="ts">
  import MoreGridSmall from "@iconify-svelte/ci/more-grid-small";

  import type { TagGroupInfo } from "./types";
  import TagGroups from "./TagGroups.svelte";
  import TagPill from "./TagPill.svelte";

  interface Props {
    tags: TagGroupInfo[];
  };

  let { tags }: Props = $props();
</script>


<div class="flex flex-col gap-2">
  {#each tags as tagGroup}
    <div class="flex flex-row flex-wrap items-center gap-2">
      <button
        class={[
          "text-sm h-4 w-4 rounded-sm tag-btn",
          "tag-btn--off",  // TODO: Depend on group status
        ]}
        aria-label="Toggle group"
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
        <TagGroups tags={tagGroup.subgroups} />
      </div>
    {/if}
  {/each}
</div>
