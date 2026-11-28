<script lang="ts">
  import IconRotateCCW from "@lucide/svelte/icons/rotate-ccw";
  import IconCheckCheck from "@lucide/svelte/icons/check-check";
  import IconX from "@lucide/svelte/icons/x";
  import { onDestroy, untrack } from "svelte";
  import type { WidgetProps } from "./anywidget.svelte";
  import { useTrait, sendMessage } from "./anywidget.svelte";
  import { ImageLoader } from "./imageLoader";
  import type { Shortcut } from "./hotkeys";
  import type { ViewerTraits } from "./types";
  import Viewer from "./Viewer.svelte";
  import Button from "./Button.svelte";

  interface ReviewTagInfo {
    path: string[];
    path_str: string;
    origin: string;
    /** The original confidence (before the review). */
    confidence: number;
    present: boolean;
    /** Whether there's a saved decision for the tag. */
    reviewed: boolean;
  };

  type Traits = ViewerTraits & {
    review_tags: ReviewTagInfo[];
  };

  // These mustn't ever change, so we get rid of reactivity here.
  let _props: WidgetProps<Traits> = $props();
  let { model, experimental } = untrack(() => _props);

  const loader = new ImageLoader(experimental);
  onDestroy(() => loader.dispose());

  const reviewTags = useTrait(model, "review_tags");

  function toggleTag(tag: ReviewTagInfo) {
    sendMessage(model, "toggle_tag", { path: tag.path, present: !tag.present });
  }

  function setAll(present: boolean) {
    sendMessage(model, "set_all", { present });
  }

  function revertImage() {
    sendMessage(model, "revert_image");
  }

  let shortcuts: Shortcut[] = $derived([
    ...reviewTags.value.slice(0, 9).map((tag, idx) => ({
      code: `Digit${idx + 1}`,
      callback: () => toggleTag(tag),
    })),
    { code: "KeyA", callback: () => setAll(true) },
    { code: "KeyX", callback: () => setAll(false) },
    { code: "Backspace", callback: revertImage },
  ]);
</script>

<Viewer
  {model}
  {experimental}
  {loader}
  {shortcuts}
  help={[
    { keys: [["1"], ["..."], ["9"]], text: "toggle tag" },
    { keys: [["A"]], text: "keep all" },
    { keys: [["X"]], text: "remove all" },
    { keys: [["Backspace"]], text: "reset current image" },
  ]}
  imageButtons={[
    {
      icon: IconRotateCCW,
      title: "Reset image tags",
      onclick: revertImage,
    },
  ]}
>
  {#snippet side()}
    <div class="flex flex-row flex-wrap items-center gap-2">
      <Button size="sm" icon={IconCheckCheck} onclick={() => setAll(true)}>Keep all</Button>
      <Button size="sm" icon={IconX} onclick={() => setAll(false)}>Remove all</Button>
      <span class="text-xs text-slate-500">Leaving the image keeps the tags that are on, and removes the rest</span>
    </div>

    <div class="flex flex-col gap-1">
      {#each reviewTags.value as tag, idx (tag.path_str)}
        <button
          class={[
            "flex flex-row items-center gap-3 px-3 py-1.5 rounded-lg text-sm text-left tag-btn",
            tag.present ? "tag-btn--on" : "tag-btn--off",
          ]}
          title={`${tag.path_str} (origin: ${tag.origin})`}
          onclick={() => toggleTag(tag)}
        >
          <span class="w-4 shrink-0 text-xs font-semibold text-slate-500">{idx < 9 ? idx + 1 : ""}</span>
          <span class={["flex-1 min-w-0 truncate font-medium", !tag.present && "line-through"]}>{tag.path_str}</span>
          {#if tag.reviewed}
            <span class="text-xs text-emerald-700">{tag.present ? "kept" : "removed"}</span>
          {/if}
          <span class="w-24 shrink-0 h-1.5 rounded-full bg-slate-200 overflow-hidden" aria-hidden="true">
            <span class="block h-full bg-slate-500" style:width={`${tag.confidence * 100}%`}></span>
          </span>
          <span class="w-10 shrink-0 text-right text-xs tabular-nums text-slate-600">{Math.round(tag.confidence * 100)}%</span>
        </button>
      {:else}
        <span class="text-sm text-gray-400">No tags to review</span>
      {/each}
    </div>
  {/snippet}
</Viewer>
