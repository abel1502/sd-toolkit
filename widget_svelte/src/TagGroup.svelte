<script lang="ts">
  import MoreGridSmall from "@iconify-svelte/ci/more-grid-small";

  import type { TagGroupInfo, ToggleGroupEvent, ToggleTagEvent } from "./types";
  import { isGroupPresent } from "./utils";
  import TagPill from "./TagPill.svelte";

  interface Props {
    idx: number;
    tagGroup: TagGroupInfo;
    tagPresence: Record<string, boolean>;
    toggleGroup: (event: ToggleGroupEvent) => void;
    toggleTag: (event: ToggleTagEvent) => void;
  };

  let { idx, tagGroup, tagPresence, toggleGroup, toggleTag }: Props = $props();

  let groupPresent = $derived(isGroupPresent(tagGroup, tagPresence));
</script>


<div
  class="flex flex-row flex-wrap items-center gap-2 p-2 border border-gray-300 bg-gray-50 rounded-lg"
  style:--level={tagGroup.level}
  style:margin-left="calc(var(--spacing) * var(--level) * 8)"
>
  <button
    class={[
      "text-sm h-6 w-6 rounded-sm tag-btn ",
      groupPresent ? "tag-btn--on" : "tag-btn--off",
    ]}
    aria-label="Toggle group"
    onclick={() => toggleGroup({
      idx,
      present: !groupPresent,
    })}
  >
    {#if tagGroup.hotkey}
      <span class="m-auto text-center font-semibold text-slate-600">{tagGroup.hotkey}</span>
    {:else}
      <MoreGridSmall width="1em" height="1em" class="m-auto align-middle" />
    {/if}
  </button>
  
  {#each tagGroup.tags as tag (tag.path_str)}
    <TagPill {tag} present={tagPresence[tag.path_str]} {toggleTag} />
  {/each}
</div>
