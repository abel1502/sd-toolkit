<script lang="ts">
  import type { TagInfo } from "./types";

  interface Props {
    tag: TagInfo;
    class?: string;
  };

  let { tag, class: extraClass = "" }: Props = $props();
</script>

<button
  class={[
    "px-4 py-2 h-min rounded-full text-sm font-medium text-center tag-btn",
    tag.present ? "tag-btn--on" : "tag-btn--off",
    extraClass,
  ]}
  // onclick={() => toggleTag(tag.path)}
>
  {tag.tag}
</button>
