<script lang="ts">
  import type { SwitchImageEvent } from "./types";
  import IconChevronLeft from "@lucide/svelte/icons/chevron-left";
  import IconChevronRight from "@lucide/svelte/icons/chevron-right";

  interface Props {
    curImageIdx: number;
    totalImages: number;
    goToImage: (event: SwitchImageEvent) => void;
    nextImage: () => void;
    prevImage: () => void;
    class?: string;
  };

  let { curImageIdx, totalImages, goToImage, nextImage, prevImage, class: extraClass = "" }: Props = $props();

  let percentage = $derived(totalImages == 0 ? 1 : curImageIdx / totalImages);

  function progressbarIdx(event: MouseEvent): number {
    let bb = (event.currentTarget as HTMLElement).getBoundingClientRect();

    let fraction = (event.clientX - bb.left) / bb.width;
    fraction = Math.max(0, Math.min(1, fraction));

    return Math.round(fraction * totalImages);
  }

  let tooltipShow: boolean = $state(false);
  let tooltipX: number = $state(0);
  let tooltipIdx: number = $state(0);

  let pointerHandler = (event: PointerEvent) => {
    tooltipX = event.clientX;
    tooltipIdx = progressbarIdx(event);
  }
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
    <IconChevronLeft width="1em" height="1em" class="align-middle" />
    Previous
  </button>

  <div class="flex-1 relative">
    <div class="py-[1.5em]">
      <div class="h-2 bg-gray-200 rounded-full cursor-pointer overflow-hidden"
        onmousedown={(event) => goToImage({ idx: progressbarIdx(event) })}
        onpointerenter={(event) => { tooltipShow = true; pointerHandler(event); }}
        onpointermove={pointerHandler}
        onpointerleave={() => { tooltipShow = false; }}
        role="slider"
        aria-valuenow={curImageIdx}
        aria-valuemin="0"
        aria-valuemax={totalImages}
        tabindex={-1}
      >
        <div
          class="h-full bg-blue-500 transition-[width] duration-300"
          style:--progress={percentage}
          style:width="calc(var(--progress) * 100%)"
          style:anchor-name="--progressbar"
        ></div>
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
    <span
      class="fixed block pointer-events-none text-black -translate-x-1/2 z-50 px-1 bg-gray-100 border border-gray-300 shadow-sm"
      hidden={!tooltipShow}
      style:position-anchor="--progressbar"
      style:bottom="calc(anchor(top) + 0.25em)"
      style:left={`${tooltipX}px`}
    >
      {tooltipIdx}/{totalImages}
    </span>
  </div>

  <button 
    class="nav-button pl-4 pr-3"
    onclick={nextImage}  // TODO: Explicitly specify whether the current image should be saved? Yes for next, no for prev and seek? Changing auto-saves already. Maybe also a button + hotkey to accept the image as-is? But then, I guess, space/next is already that. Just gotta document as much.
    disabled={curImageIdx == totalImages}
  >
    Next
    <IconChevronRight width="1em" height="1em" class="align-middle" />
  </button>
</div>

<style lang="postcss">
  @reference "./app.css";
  
  .nav-button {
    @apply flex flex-row py-2 gap-2 items-center border rounded not-disabled:hover:bg-gray-50 text-gray-700 disabled:text-gray-300;
  }
</style>
