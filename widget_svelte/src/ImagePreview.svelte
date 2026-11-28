<script lang="ts">
  import type { Snippet } from "svelte";
  import IconLoader from "@lucide/svelte/icons/loader-circle";
  import IconCheck from "@lucide/svelte/icons/check";
  import IconAlert from "@lucide/svelte/icons/circle-alert";
  import { fade } from "svelte/transition";

  import type { ImageButton, MarkStyle } from "./types";
  import type { Notice } from "./notifier.svelte";

  interface Props {
    url: string | null;
    loading?: boolean;
    error?: string | null;
    badge?: MarkStyle | null;
    buttons?: ImageButton[];
    /** A status message shown over the image (e.g. when an action fails). */
    notice?: Notice | null;
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
    notice = null,
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

  {#if notice}
    <div
      class={[
        "absolute bottom-10 left-0 m-2 max-w-[calc(100%-1rem)] flex flex-row items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs shadow-sm ring-1 whitespace-pre-wrap break-words",
        notice.kind == "error" ? "bg-red-50 text-red-700 ring-red-200" : "bg-white/90 text-slate-700 ring-slate-200",
      ]}
      transition:fade={{ duration: 150 }}
    >
      {#if notice.kind == "pending"}
        <IconLoader class="w-3.5 h-3.5 shrink-0 animate-spin" />
      {:else if notice.kind == "success"}
        <IconCheck class="w-3.5 h-3.5 shrink-0 text-emerald-600" />
      {:else}
        <IconAlert class="w-3.5 h-3.5 shrink-0" />
      {/if}
      {notice.text}
    </div>
  {/if}

  {#if buttons.length > 0}
    <div class="absolute bottom-0 right-0 px-2 py-1 bg-black/20 h-10 flex gap-2 items-center rounded-tl-lg">
      {#each buttons as { icon: Icon, title, onclick, status = "idle" }}
        <button
          class={["text-white rounded-full", status == "success" && "flash-success", status == "error" && "flash-error"]}
          {title}
          aria-busy={status == "pending"}
          {onclick}
        >
          {#if status == "pending"}
            <IconLoader class="w-6 h-6 animate-spin" />
          {:else}
            <Icon class="w-6 h-6" />
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .flash-success {
    animation: flash-success 900ms ease-out;
  }

  .flash-error {
    animation: flash-error 1500ms ease-out;
  }

  @keyframes flash-success {
    from {
      color: rgb(110 231 183);
      filter: drop-shadow(0 0 4px rgb(52 211 153));
    }
  }

  @keyframes flash-error {
    from {
      color: rgb(252 165 165);
      filter: drop-shadow(0 0 4px rgb(248 113 113));
    }
  }
</style>
