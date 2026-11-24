<script lang="ts">
  import type { Snippet } from "svelte";
  import IconLoader from "@lucide/svelte/icons/loader-circle";

  import type { ImageButton, MarkStyle } from "./types";

  interface Props {
    url: string | null;
    loading?: boolean;
    error?: string | null;
    badge?: MarkStyle | null;
    buttons?: ImageButton[];
    /** Replaces the plain `<img>`. */
    content?: Snippet;
    class?: string;
  };

  let {
    url,
    loading = false,
    error = null,
    badge = null,
    buttons = [],
    content,
    class: extraClass = "",
  }: Props = $props();
</script>

<div class={[
  "relative grid place-items-center aspect-square bg-gray-100 rounded-lg border border-gray-300 overflow-hidden",
  extraClass,
]}>
  {#if content}
    {@render content()}
  {:else if url}
    <img src={url} alt="Preview" class="w-full h-full object-contain aspect-square"/>
  {:else if error}
    <span class="text-red-500 text-sm text-center p-4 break-all">{error}</span>
  {:else if !loading}
    <span class="text-gray-400 text-sm text-center">No Image</span>
  {/if}

  {#if loading}
    <div class="absolute top-0 left-0 m-2 text-gray-500" title="Loading">
      <IconLoader class="w-6 h-6 animate-spin" />
    </div>
  {/if}

  {#if badge}
    <div
      class="absolute top-0 right-0 m-1.5 px-2 py-0.5 rounded-full text-xs font-semibold text-white shadow-sm"
      style:background-color={badge.color}
    >
      {badge.label}
    </div>
  {/if}

  {#if buttons.length > 0}
    <div class="absolute bottom-0 right-0 px-2 py-1 bg-black/20 h-10 flex gap-2 items-center rounded-tl-lg">
      {#each buttons as { icon: Icon, title, onclick }}
        <button class="text-white" {title} {onclick}>
          <Icon class="w-6 h-6" />
        </button>
      {/each}
    </div>
  {/if}
</div>
