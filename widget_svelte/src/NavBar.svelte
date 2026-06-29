<script lang="ts">
  import type { SwitchImageEvent } from "./types";
  import ChevronLeft from "@iconify-svelte/ci/chevron-left";
  import ChevronRight from "@iconify-svelte/ci/chevron-right";

  interface Props {
    curImageIdx: number;
    totalImages: number;
    nextImage: () => void;
    prevImage: () => void;
    class?: string;
  };

  let { curImageIdx, totalImages, nextImage, prevImage, class: extraClass = "" }: Props = $props();

  let percentage = $derived(totalImages == 0 ? 1 : curImageIdx / totalImages);
</script>

<div class={[
  "w-full flex flex-row items-center gap-4",
  extraClass,
]}>
  <button 
    class="nav-button pl-3 pr-4"
    onclick={prevImage}
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
        <!-- TODO: click to seek (maybe also a tooltip for which image you're hovering over) -->
        <!-- TODO: canvas showing the status for each image, instead of a single solid progressbar? -->
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
    class="nav-button pl-4 pr-3"
    onclick={nextImage}  // TODO: Explicitly specify whether the current image should be saved? Yes for next, no for prev and seek? Changing auto-saves already. Maybe also a button + hotkey to accept the image as-is? But then, I guess, space/next is already that. Just gotta document as much.
    disabled={curImageIdx == totalImages}
  >
    Next
    <ChevronRight width="1em" height="1em" class="align-middle" />
  </button>
</div>

<style lang="postcss">
  @reference "./app.css";
  
  .nav-button {
    @apply flex flex-row py-2 gap-2 items-center border rounded not-disabled:hover:bg-gray-50 text-gray-700 disabled:text-gray-300;
  }
</style>
