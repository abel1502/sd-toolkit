<script lang="ts">
  import type { TagGroupInfo, ToggleGroupEvent, ToggleTagEvent } from "./types";
  import TagGroup from "./TagGroup.svelte";

  interface Props {
    tagGroups: TagGroupInfo[];
    tagPresence: Record<string, boolean>;
    toggleGroup: (event: ToggleGroupEvent) => void;
    toggleTag: (event: ToggleTagEvent) => void;
    class?: string;
  };

  let { tagGroups, tagPresence, toggleGroup, toggleTag, class: extraClass = "" }: Props = $props();
</script>


<div class={["flex flex-col gap-2", extraClass]}>
  {#each tagGroups as tagGroup, idx (idx)}
    <TagGroup {idx} {tagGroup} {tagPresence} {toggleGroup} {toggleTag} />
  {/each}
</div>
