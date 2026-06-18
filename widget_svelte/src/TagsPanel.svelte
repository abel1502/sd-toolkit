<script lang="ts">
  import MoreGridSmall from "@iconify-svelte/ci/more-grid-small";

  import type { TagGroupInfo, ToggleGroupEvent, ToggleTagEvent } from "./types";
  import TagGroup from "./TagGroup.svelte";
  import TagPill from "./TagPill.svelte";

  interface Props {
    tagGroups: TagGroupInfo[];
    toggleGroup: (event: ToggleGroupEvent) => void;
    toggleTag: (event: ToggleTagEvent) => void;
  };

  let { tagGroups, toggleGroup, toggleTag }: Props = $props();
</script>


<div class="flex flex-col gap-2">
  {#each tagGroups as tagGroup, idx}
    <TagGroup {idx} {tagGroup} {toggleGroup} {toggleTag} />
  {/each}
</div>
