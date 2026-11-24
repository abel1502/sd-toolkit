<script lang="ts">
  import IconLoader from "@lucide/svelte/icons/loader-circle";

  import type { ImageLoader } from "./imageLoader";

  interface Props {
    loader: ImageLoader;
    path: string;
    /** The image's version key. A change triggers a reload. */
    imageKey: string;
    size?: number;
    class?: string;
  };

  let { loader, path, imageKey, size = 160, class: extraClass = "" }: Props = $props();

  let url: string | null = $state(null);
  let error: string | null = $state(null);

  $effect(() => {
    const request = { path, thumbnail: size };
    const key = imageKey;
    let cancelled = false;

    error = null;
    loader.load(request, key).then(
      (result) => { if (!cancelled) url = result.url; },
      (e) => { if (!cancelled) { url = null; error = String(e); } },
    );

    return () => { cancelled = true; };
  });
</script>

<div
  class={["grid place-items-center bg-gray-100 rounded-md border border-gray-300 overflow-hidden", extraClass]}
  style:width="{size}px"
  style:height="{size}px"
>
  {#if url}
    <img src={url} alt={path} class="w-full h-full object-contain" />
  {:else if error}
    <span class="text-xs text-red-500 p-1 break-all" title={error}>Failed to load</span>
  {:else}
    <IconLoader class="w-5 h-5 text-gray-400 animate-spin" />
  {/if}
</div>
