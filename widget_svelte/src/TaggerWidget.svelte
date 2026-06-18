<script lang="ts">
  import type { AnyModel } from "@anywidget/types";
  import { Confetti } from "svelte-confetti";
  import { slide } from "svelte/transition";
  import type { TagGroupInfo, ToggleTagEvent, ToggleGroupEvent, SwitchImageEvent } from "./types";
  import TagsPanel from "./TagsPanel.svelte";
  import NavBar from "./NavBar.svelte";

  // TODO: Match the python side.
  // - Nested tag groups. Note: groups must have a button for toggling the whole thing at once.
  // - Hotkeys. A switch in the corner to listen for them. Actually make that a bottom row with the switch and a description of the hotkeys.
  // - Show when an image was already handled (a checkmark?)
  // - Image zoom-in. Or just open file externally. Also maybe the file path diplayed somewhere to copy -- or even as a widget trait for python-side consumption only
  // - Break up into subcomponents!
  // - Undo, or at least discarding the changes for the current image.
  // - Clicking on the progressbar to seek? Coloring progressbar 
  interface Bindings {
    // Input only
    image: string;
    tags: TagGroupInfo[];
    image_idx: number;
    image_count: number;

    // Output only
    toggle_tag: ToggleTagEvent | null;
    toggle_group: ToggleGroupEvent | null;
    switch_image: SwitchImageEvent | null;
  }

  interface Props {
    model: AnyModel<Bindings>;
    bindings: Bindings;
  };

  let { model, bindings }: Partial<Props> = $props();

  let image = $derived(bindings?.image || "");
  let tags = $derived(bindings?.tags || []);
  let curImageIdx = $derived(bindings?.image_idx || 0);
  let totalImages = $derived(bindings?.image_count || 0);

  let percentage = $derived(totalImages == 0 ? 1 : curImageIdx / totalImages);
  let is_done = $derived(curImageIdx == totalImages);

  function toggleTag(event: ToggleTagEvent) {
    // TODO: Add a spinner while waiting for updates from python somehow?
    if (!bindings) return;

    bindings.toggle_tag = event;
  }

  function toggleGroup(event: ToggleGroupEvent) {
    // TODO: Add a spinner while waiting for updates from python somehow?
    if (!bindings) return;

    bindings.toggle_group = event;
  }

  function goToImage(event: SwitchImageEvent) {
    // TODO: Add a spinner while waiting for updates from python somehow?
    if (!bindings) return;

    event.idx = Math.max(0, Math.min(event.idx, totalImages));

    bindings.switch_image = event;
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
    <div class="flex flex-row gap-6 resize-y min-h-48 h-64 max-h-[50vw] overflow-hidden" transition:slide>
      <div class="grid place-items-center h-full min-h-full aspect-square bg-gray-100 rounded-lg border border-gray-300 overflow-hidden">
        {#if image}
          <img src={image} alt="Preview" class="w-full h-full object-contain"/>
        {:else}
          <span class="text-gray-400 text-sm text-center">No Image</span>
        {/if}
      </div>
      
      <div class="flex-1 py-1">
        <TagsPanel tagGroups={tags} {toggleGroup} {toggleTag} />
      </div>
    </div>
  {/if}

  <NavBar class="mt-6" {curImageIdx} {totalImages} {goToImage} />
</div>
