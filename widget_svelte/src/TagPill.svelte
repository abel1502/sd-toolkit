<script lang="ts">
  import type { TagInfo, ToggleTagEvent } from "./types";

  interface Props {
    tag: TagInfo;
    class?: string;
    toggleTag: (event: ToggleTagEvent) => void;
  };

  let { tag, class: extraClass = "", toggleTag }: Props = $props();
</script>

<button
  class={[
    "px-4 py-2 h-min rounded-full text-sm font-medium text-center tag-btn",
    tag.present ? "tag-btn--on" : "tag-btn--off",
    extraClass,
  ]}
  onclick={() => toggleTag({
    path: tag.path,
    present: !tag.present
  })}
>
  {tag.tag}
</button>
