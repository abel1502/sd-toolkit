<script lang="ts">
  import MoreGridSmall from "@iconify-svelte/ci/more-grid-small";

  import type { TagGroupInfo, ToggleGroupEvent, ToggleTagEvent } from "./types";
  import TagGroup from "./TagGroup.svelte";

  interface Props {
    tagGroups: TagGroupInfo[];
    toggleGroup: (event: ToggleGroupEvent) => void;
    toggleTag: (event: ToggleTagEvent) => void;
    class?: string;
  };

  let { tagGroups, toggleGroup, toggleTag, class: extraClass = "" }: Props = $props();
</script>


<div class={["flex flex-col gap-2", extraClass]}>
  {#each tagGroups as tagGroup, idx (idx)}
    <TagGroup {idx} {tagGroup} {toggleGroup} {toggleTag} />
  {/each}
</div>
