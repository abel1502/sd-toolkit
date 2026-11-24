<script lang="ts">
  import type { MarkStyle, SwitchImageEvent } from "./types";
  import IconChevronLeft from "@lucide/svelte/icons/chevron-left";
  import IconChevronRight from "@lucide/svelte/icons/chevron-right";

  interface Props {
    curImageIdx: number;
    totalImages: number;
    /** The maximum index that can be navigated to (`totalImages` if there's a done screen). */
    maxIdx: number;
    marks?: number[];
    markStyles?: (MarkStyle | null)[];
    goToImage: (event: SwitchImageEvent) => void;
    nextImage: () => void;
    prevImage: () => void;
    class?: string;
  };

  let {
    curImageIdx,
    totalImages,
    maxIdx,
    marks = [],
    markStyles = [],
    goToImage,
    nextImage,
    prevImage,
    class: extraClass = "",
  }: Props = $props();

  // Without a done screen, the last image counts as the end
  let percentage = $derived(maxIdx <= 0 ? 1 : curImageIdx / maxIdx);

  function progressbarIdx(event: MouseEvent): number {
    let bb = (event.currentTarget as HTMLElement).getBoundingClientRect();

    let fraction = (event.clientX - bb.left) / bb.width;
    fraction = Math.max(0, Math.min(1, fraction));

    return Math.round(fraction * maxIdx);
  }

  let tooltipShow: boolean = $state(false);
  let tooltipX: number = $state(0);
  let tooltipIdx: number = $state(0);

  let pointerHandler = (event: PointerEvent) => {
    tooltipX = event.clientX;
    tooltipIdx = progressbarIdx(event);
  }

  let marksCanvas: HTMLCanvasElement | undefined = $state();
  let marksWidth: number = $state(0);
  let hasMarks = $derived(marks.some(m => m != 0));

  // Draws a strip showing the status of each image
  $effect(() => {
    if (!marksCanvas || !hasMarks) return;

    const width = Math.max(1, Math.round(marksWidth * devicePixelRatio));
    marksCanvas.width = width;
    marksCanvas.height = 1;

    const ctx = marksCanvas.getContext("2d")!;
    ctx.clearRect(0, 0, width, 1);

    const count = Math.max(1, totalImages);
    for (let i = 0; i < marks.length; i++) {
      const style = markStyles[marks[i]];
      if (!style) continue;

      ctx.fillStyle = style.color;
      const x0 = Math.floor(i / count * width);
      const x1 = Math.max(x0 + 1, Math.floor((i + 1) / count * width));
      ctx.fillRect(x0, 0, x1 - x0, 1);
    }
  });

  let markCounts = $derived.by(() => {
    const counts = new Map<number, number>();
    for (const mark of marks) {
      if (mark != 0) counts.set(mark, (counts.get(mark) ?? 0) + 1);
    }
    return [...counts.entries()].sort(([a], [b]) => a - b);
  });
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
      <div class="relative h-2 bg-gray-200 rounded-full cursor-pointer overflow-hidden"
        onmousedown={(event) => goToImage({ idx: progressbarIdx(event) })}
        onpointerenter={(event) => { tooltipShow = true; pointerHandler(event); }}
        onpointermove={pointerHandler}
        onpointerleave={() => { tooltipShow = false; }}
        role="slider"
        aria-valuenow={curImageIdx}
        aria-valuemin="0"
        aria-valuemax={maxIdx}
        tabindex={-1}
        bind:clientWidth={marksWidth}
      >
        <div
          class="h-full bg-blue-500 transition-[width] duration-300"
          style:--progress={percentage}
          style:width="calc(var(--progress) * 100%)"
          style:anchor-name="--progressbar"
        ></div>
        {#if hasMarks}
          <!-- Per-image statuses, over the bottom half of the progressbar -->
          <canvas
            bind:this={marksCanvas}
            class="absolute left-0 bottom-0 w-full h-1/2 pointer-events-none"
            style:image-rendering="pixelated"
          ></canvas>
        {/if}
      </div>
    </div>
    <span
      class="absolute block text-black"
      style:position-anchor="--progressbar"
      style:position-area="bottom span-left"
    >
      {Math.min(curImageIdx + 1, totalImages)}/{totalImages}
    </span>
    {#if markCounts.length > 0}
      <span class="absolute right-0 bottom-0 flex gap-3 text-xs text-slate-600">
        {#each markCounts as [mark, count] (mark)}
          {@const style = markStyles[mark]}
          {#if style}
            <span class="flex items-center gap-1">
              <span class="inline-block w-2 h-2 rounded-full" style:background-color={style.color}></span>
              {style.label}: {count}
            </span>
          {/if}
        {/each}
      </span>
    {/if}
    <span
      class="fixed block pointer-events-none text-black -translate-x-1/2 z-50 px-1 bg-gray-100 border border-gray-300 shadow-sm"
      hidden={!tooltipShow}
      style:position-anchor="--progressbar"
      style:bottom="calc(anchor(top) + 0.25em)"
      style:left={`${tooltipX}px`}
    >
      {Math.min(tooltipIdx + 1, totalImages)}/{totalImages}
    </span>
  </div>

  <button
    class="nav-button pl-4 pr-3"
    onclick={nextImage}  // TODO: Explicitly specify whether the current image should be saved? Yes for next, no for prev and seek? Changing auto-saves already. Maybe also a button + hotkey to accept the image as-is? But then, I guess, space/next is already that. Just gotta document as much.
    disabled={curImageIdx >= maxIdx}
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
