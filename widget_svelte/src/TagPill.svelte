<script lang="ts">
  import type { TagInfo, ToggleTagEvent } from "./types";

  interface Props {
    tag: TagInfo;
    present: boolean;
    class?: string;
    toggleTag: (event: ToggleTagEvent) => void;
  };

  let { tag, present, class: extraClass = "", toggleTag }: Props = $props();
</script>

<button
  class={[
    "px-4 py-2 h-min rounded-full text-sm font-medium text-center tag-btn",
    present ? "tag-btn--on" : "tag-btn--off",
    extraClass,
  ]}
  title={tag.path_str}
  onclick={() => toggleTag({
    path: tag.path,
    present: !present
  })}
>
  {tag.tag}
</button>
