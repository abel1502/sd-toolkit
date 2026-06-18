<script lang="ts">
  import MoreGridSmall from "@iconify-svelte/ci/more-grid-small";

  import type { TagGroupInfo } from "./types";
  import TagGroup from "./TagGroup.svelte";
  import TagPill from "./TagPill.svelte";

  interface Props {
    tagGroups: TagGroupInfo[];
  };

  let { tagGroups }: Props = $props();
</script>


<div class="flex flex-col gap-2">
  {#each tagGroups as tagGroup}
    <TagGroup tagGroup={tagGroup} />
  {/each}
</div>
