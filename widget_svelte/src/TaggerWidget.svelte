<script lang="ts">
  import type { AnyModel } from "@anywidget/types";
  import { Confetti } from "svelte-confetti";
  import { slide } from "svelte/transition";
  import ChevronLeft from "@iconify-svelte/ci/chevron-left";
  import ChevronRight from "@iconify-svelte/ci/chevron-right";
  /*
  Used icon packs: (attribution, as per their licenses)
  - coolicons by Kryston Schwarze, CC BY 4.0
    https://icon-sets.iconify.design/ci/
  */

  interface TagGroupInfo {
    tags: {
      tag: string;
      path: string[];
      present: boolean;
    }[];
    subgroups: TagGroupInfo[];
    hotkey: string | null;
  }

  // TODO: Match the python side.
  // - Nested tag groups. Note: groups must have a button for toggling the whole thing at once.
  // - Hotkeys
  // - Show when an image was already handled (a checkmark?)
  // - Maybe let the user resize the widget? Would be nice.
  // - Image zoom-in. Or just open file externally. Also maybe the file path diplayed somewhere to copy -- or even as a widget trait for python-side consumption only
  // - Break up into subcomponents!
  interface Bindings {
    // Input only
    image: string;
    tags: TagGroupInfo[];
    image_idx: number;
    image_count: number;
    // Output only
    toggle_tag: {
      path: string[];
      present: boolean;
    };
    switch_image: number;
  }

  interface Props {
    model?: AnyModel<Bindings>;
    bindings?: Bindings;
  };

  let { model, bindings }: Props = $props();

  let image = $derived(bindings?.image || "");
  let tags = $derived(bindings?.tags || []);
  let curImageIdx = $derived(bindings?.image_idx || 0);
  let totalImages = $derived(bindings?.image_count || 0);

  let percentage = $derived(totalImages == 0 ? 1 : curImageIdx / totalImages);
  let is_done = $derived(curImageIdx == totalImages);

  function toggleTag(event: {
    path: string[],
    present: boolean,
  }) {
    // TODO: Add a spinner while waiting for updates from python somehow?
    if (!bindings) return;

    bindings.toggle_tag = event;
  }

  function goToImage(idx: number) {
    // TODO: Add a spinner while waiting for updates from python somehow?
    if (!bindings) return;

    idx = Math.max(0, Math.min(idx, totalImages));

    bindings.switch_image = idx;
  }

  let width: number | undefined = $state()
</script>


<div
  class="flex flex-col w-full min-w-xl max-w-4xl p-4 border rounded-lg bg-white shadow-sm"
  bind:clientWidth={width}
>
  {#if is_done}
    <div class="grid place-items-center h-16 border p-4 rounded-lg bg-green-200 shadow-sm">
      {#if totalImages > 0}
        <Confetti x={[-width / 400.0, width / 400.0]} y={[-0.5, 0.25]} amount={100} />
      {/if}
      <span class="text-green-800 font-bold absolute">Done!</span>
    </div>
  {:else}
    <div class="flex flex-row gap-6" transition:slide>
      <div class="flex-1 flex aspect-square bg-gray-100 rounded-lg items-center justify-center border">
        {#if image}
          <img src={image} alt="Preview" class="w-ful h-full object-contain rounded-lg overflow-hidden"/>
        {:else}
          <span class="text-gray-400 text-sm">No Image</span>
        {/if}
      </div>
      
      <div class="flex-1 flex flex-row flex-wrap gap-2 py-1">
        <!-- {#each Object.keys(tags) as tagName}
          <button
            class={[
              "px-4 py-2 rounded-full text-sm font-medium transition-colors duration-200 h-min",
              tags[tagName] 
                ? "bg-blue-100 text-blue-800 ring-1 ring-blue-300" 
                : "bg-gray-100 text-gray-600 hover:bg-gray-200",
            ]}
            onclick={() => toggleTag(tagName)}
          >
            {tagName}
          </button>
        {/each} -->
      </div>
    </div>
  {/if}

  <div class="mt-6 mx-2 flex flex-row items-center gap-4">
    <button 
      class="flex flex-row p-2 pl-3 pr-4 gap-2 items-center border rounded not-disabled:hover:bg-gray-50 not-disabled:cursor-pointer text-gray-700 disabled:text-gray-300"
      onclick={() => goToImage(curImageIdx - 1)}
      disabled={curImageIdx == 0}
    >
      <ChevronLeft width="1em" height="1em" class="align-middle" />
      Previous
    </button>

    <div class="flex-1 relative">
      <div class="py-[1.5em]">
        <div class="h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            class="h-full bg-blue-500 transition-[width] duration-300"
            style:--progress={percentage}
            style:width="calc(var(--progress) * 100%)"
            style:anchor-name="--progressbar"
          ></div>
        </div>
      </div>
      <span
        class="absolute block text-black"
        style:position-anchor="--progressbar"
        style:position-area="bottom span-left"
      >
        {curImageIdx}/{totalImages}
      </span>
    </div>

    <button 
      class="flex flex-row p-2 pl-4 pr-3 gap-2 items-center border rounded not-disabled:hover:bg-gray-50 not-disabled:cursor-pointer text-gray-700 disabled:text-gray-300"
      onclick={() => goToImage(curImageIdx + 1)}
      disabled={curImageIdx == totalImages}
    >
      Next
      <ChevronRight width="1em" height="1em" class="align-middle" />
    </button>
  </div>

</div>
