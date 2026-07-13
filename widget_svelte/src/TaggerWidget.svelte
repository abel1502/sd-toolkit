<script lang="ts">
  import type { AnyModel } from "@anywidget/types";
  import { Confetti } from "svelte-confetti";
  import { slide } from "svelte/transition";
  import ArrowsReload01 from "@iconify-svelte/ci/arrows-reload-01";
  import MagnifyingGlassPlus from "@iconify-svelte/ci/magnifying-glass-plus";
  import type { TagGroupInfo, ToggleTagEvent, ToggleGroupEvent, SwitchImageEvent } from "./types";
  import TagsPanel from "./TagsPanel.svelte";
  import NavBar from "./NavBar.svelte";
  import HotkeyBar from "./HotkeyBar.svelte";
  import ImagePreview from "./ImagePreview.svelte";

  // TODO:
  // - Show when an image was already handled (a checkmark?)
  // - Clicking on the progressbar to seek? Coloring progressbar based on which images are already handled?
  interface Bindings {
    // Input only
    image: string;
    tag_groups: TagGroupInfo[];
    image_idx: number;
    image_count: number;
    image_saved: boolean;
  }

  interface Props {
    model: AnyModel<Bindings>;
    bindings: Bindings;
  };

  let { model, bindings }: Partial<Props> = $props();

  let image = $derived(bindings?.image || "");
  let tagGroups = $derived(bindings?.tag_groups || []);
  let curImageIdx = $derived(bindings?.image_idx || 0);
  let totalImages = $derived(bindings?.image_count || 0);
  let imageSaved = $derived(bindings?.image_saved || false);

  let is_done = $derived(curImageIdx == totalImages);

  function toggleTag(event: ToggleTagEvent) {
    // TODO: Add a spinner while waiting for updates from python somehow?
    model?.send({
      kind: "custom",
      type: "toggle_tag",
      ...event,
    });
  }

  function toggleGroup(event: ToggleGroupEvent) {
    // TODO: Add a spinner while waiting for updates from python somehow?
    model?.send({
      kind: "custom",
      type: "toggle_group",
      ...event,
    });
  }

  function goToImage(event: SwitchImageEvent) {
    // TODO: Add a spinner while waiting for updates from python somehow?
    event.idx = Math.max(0, Math.min(event.idx, totalImages));

    model?.send({
      kind: "custom",
      type: "switch_image",
      ...event,
    });
  }

  function nextImage() {
    goToImage({ idx: curImageIdx + 1 });
  }

  function prevImage() {
    goToImage({ idx: curImageIdx - 1 });
  }

  function revertImage() {
    model?.send({
      kind: "custom",
      type: "revert_image",
    });
  }

  function viewImage() {
    model?.send({
      kind: "custom",
      type: "view_image",
    })
  }

  let width: number | undefined = $state()
</script>


<div
  class="flex flex-col w-full resize-x min-w-2xl max-w-full p-4 border rounded-lg bg-white shadow-sm overflow-hidden"
  bind:clientWidth={width}
>
  {#if is_done}
    <div class="grid place-items-center h-16 border border-green-300 p-4 rounded-lg bg-green-200 shadow-sm">
      {#if totalImages > 0}
        <Confetti x={[-width / 400.0, width / 400.0]} y={[-0.5, 0.25]} amount={100} />
      {/if}
      <span class="text-green-800 font-bold absolute">Done!</span>
    </div>
  {:else}
    <div class="flex flex-row gap-6 resize-y min-h-48 h-64 overflow-hidden" transition:slide>
      <ImagePreview class="h-full max-h-[35vw]" {image} {imageSaved} buttons={[
        {
          icon: ArrowsReload01,
          title: "Reset image tags",
          onclick: revertImage,
        },
        {
          icon: MagnifyingGlassPlus,
          title: "Open in external viewer",
          onclick: viewImage,
        }
      ]} />
      
      <div class="flex-1 py-1 overflow-y-auto scrollbar-hidden">
        <TagsPanel {tagGroups} {toggleGroup} {toggleTag} />
      </div>
    </div>
  {/if}

  <NavBar class="mt-6" {curImageIdx} {totalImages} {goToImage} {nextImage} {prevImage} />

  <HotkeyBar class="mt-4" {tagGroups} {toggleGroup} {nextImage} {prevImage} {revertImage} />
</div>
