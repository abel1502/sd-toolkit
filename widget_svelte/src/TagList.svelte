<script lang="ts">
  import IconX from "@lucide/svelte/icons/x";
  import IconStar from "@lucide/svelte/icons/star";

  import type { TagDisplay } from "./types";

  interface Props {
    tags: TagDisplay[];
    /** If specified, tags get remove buttons. */
    onremove?: (tag: TagDisplay) => void;
    class?: string;
  };

  let { tags, onremove, class: extraClass = "" }: Props = $props();

  // Danbooru's category colors
  const CATEGORY_COLORS: Record<string, string> = {
    general: "#0075f8",
    artist: "#c00004",
    copyright: "#a800aa",
    character: "#00ab2c",
    meta: "#fd9200",
  };

  function describe(tag: TagDisplay): string {
    return [
      tag.path_str,
      `category: ${tag.category}`,
      `origin: ${tag.origin}`,
      `confidence: ${tag.confidence.toFixed(3)}`,
      ...(tag.is_trigger ? ["trigger"] : []),
    ].join("\n");
  }
</script>

<div class={["flex flex-row flex-wrap gap-1.5", extraClass]}>
  {#each tags as tag (tag.path_str)}
    <span
      class="inline-flex items-center gap-1 pl-2 pr-2 py-1 rounded-full text-sm bg-gray-50 ring-1 ring-gray-300 text-gray-800"
      title={describe(tag)}
    >
      <span class="inline-block w-2 h-2 rounded-full shrink-0" style:background-color={CATEGORY_COLORS[tag.category] ?? "#9ca3af"}></span>
      {#if tag.is_trigger}
        <IconStar class="w-3.5 h-3.5 text-amber-500" />
      {/if}
      {#if tag.path.length > 1}
        <span class="text-gray-400">{tag.path.slice(0, -1).join("::")}::</span>
      {/if}
      <span>{tag.tag}</span>
      {#if tag.confidence < 1}
        <span class="text-xs text-gray-400">{tag.confidence.toFixed(2)}</span>
      {/if}
      {#if onremove}
        <button
          class="ml-0.5 rounded-full text-gray-400 hover:text-red-600 hover:bg-red-50"
          title="Remove (with subtags)"
          onclick={() => onremove(tag)}
        >
          <IconX class="w-3.5 h-3.5" />
        </button>
      {/if}
    </span>
  {:else}
    <span class="text-sm text-gray-400">No tags</span>
  {/each}
</div>
