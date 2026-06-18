<script lang="ts">
  import type { TagInfo } from "./types";

  interface Props {
    tag: TagInfo;
  };

  let { tag }: Props = $props();
</script>

<button
  class={[
    "px-4 py-2 h-min rounded-full text-sm font-medium tag-btn text-center",
    tag.present ? "tag-btn--on" : "tag-btn--off",
  ]}
  // onclick={() => toggleTag(tag.path)}
>
  {tag.tag}
</button>
