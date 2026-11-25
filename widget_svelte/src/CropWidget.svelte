<script lang="ts">
  import IconTrash from "@lucide/svelte/icons/trash-2";
  import IconLock from "@lucide/svelte/icons/lock";
  import { onDestroy, untrack } from "svelte";
  import type { WidgetProps } from "./anywidget.svelte";
  import { useTrait, sendMessage, invoke } from "./anywidget.svelte";
  import { ImageLoader } from "./imageLoader";
  import type { Shortcut } from "./hotkeys";
  import type { ViewerTraits } from "./types";
  import { TwoStepConfirm } from "./confirm.svelte";
  import Viewer from "./Viewer.svelte";
  import Button from "./Button.svelte";
  import Thumbnail from "./Thumbnail.svelte";
  import CropCanvas, { boxSize, reshapeBox, scaleBox, type Box, type Ratio } from "./CropCanvas.svelte";

  interface AspectRatio {
    label: string;
    width: number | null;
    height: number | null;
  };

  interface CropInfo {
    path: string;
    box: Box;
    locked: boolean;
    key: string;
  };

  type Traits = ViewerTraits & {
    aspect_ratios: AspectRatio[];
    crops: CropInfo[];
    image_size: [number, number];
  };

  // These mustn't ever change, so we get rid of reactivity here.
  let _props: WidgetProps<Traits> = $props();
  let { model, experimental } = untrack(() => _props);

  const loader = new ImageLoader(experimental, { maxEntries: 64 });
  onDestroy(() => loader.dispose());

  const imageKey = useTrait(model, "image_key");
  const aspectRatios = useTrait(model, "aspect_ratios");
  const crops = useTrait(model, "crops");
  const imageSize = useTrait(model, "image_size");

  let ratioIdx: number = $state(0);
  let sizeFraction: number = $state(1);
  let selected: string | null = $state(null);
  let error: string | null = $state(null);

  let ratio: Ratio = $derived.by(() => {
    const value = aspectRatios.value[ratioIdx];
    return value && value.width && value.height ? { width: value.width, height: value.height } : null;
  });

  let selectedCrop = $derived(crops.value.find(crop => crop.path == selected) ?? null);

  // Forget the selection when switching images
  $effect(() => {
    imageKey.value;
    selected = null;
    error = null;
  });

  function gcd(a: number, b: number): number {
    return b ? gcd(b, a % b) : a;
  }

  function describe(box: Box): string {
    const [w, h] = boxSize(box);
    const divisor = gcd(w, h);
    const exact = aspectRatios.value.find(r => r.width && r.height && w * r.height == h * r.width);
    const proportions = exact ? exact.label : divisor > 1 && w / divisor <= 64 ? `${w / divisor}:${h / divisor}` : (w / h).toFixed(3);
    return `${w}×${h} (${proportions})`;
  }

  async function commit(path: string | null, box: Box) {
    error = null;
    try {
      const [response] = await invoke<{ path: string }>(experimental, "set_crop", { path, box });
      selected = response.path;
    } catch (e) {
      error = String(e);
    }
  }

  function selectRatio(idx: number) {
    if (idx >= aspectRatios.value.length) return;
    ratioIdx = idx;

    // Also applies to the selected crop
    if (selectedCrop && !selectedCrop.locked && ratio) {
      const box = reshapeBox(selectedCrop.box, ratio, imageSize.value);
      if (box.some((value, i) => value != selectedCrop!.box[i])) {
        commit(selectedCrop.path, box);
      }
    }
  }

  function resizeSelected(factor: number) {
    if (!selectedCrop || selectedCrop.locked) return;
    commit(selectedCrop.path, scaleBox(selectedCrop.box, factor, ratio, imageSize.value));
  }

  const confirmDelete = new TwoStepConfirm<string>();

  function deleteCrop(path: string) {
    if (confirmDelete.request(path)) {
      sendMessage(model, "delete_crop", { path });
      if (selected == path) selected = null;
    }
  }

  let shortcuts: Shortcut[] = $derived([
    ...aspectRatios.value.slice(0, 9).map((_, idx) => ({
      code: `Digit${idx + 1}`,
      callback: () => selectRatio(idx),
    })),
    {
      code: "Delete",
      callback: () => { if (selectedCrop && !selectedCrop.locked) deleteCrop(selectedCrop.path); },
    },
    { code: "Escape", callback: () => { selected = null; } },
    { code: "BracketLeft", callback: () => resizeSelected(1 / 1.1) },
    { code: "BracketRight", callback: () => resizeSelected(1.1) },
  ]);
</script>

<Viewer
  {model}
  {loader}
  {shortcuts}
  areaClass="h-[36rem]"
  help={[
    { keys: [["1"], ["..."], ["9"]], text: "proportions" },
    { keys: [["["], ["]"]], text: "resize the selected crop" },
    { keys: [["Del"]], text: "delete the selected crop (press twice)" },
    { keys: [["Esc"]], text: "deselect" },
  ]}
>
  {#snippet imageContent(image)}
    {#if image.url && image.key == imageKey.value && imageSize.value[0] > 0}
      <CropCanvas
        imageUrl={image.url}
        imageSize={imageSize.value}
        crops={crops.value}
        bind:selected
        {ratio}
        {sizeFraction}
        oncommit={commit}
      />
    {/if}
  {/snippet}

  {#snippet side()}
    <div class="flex flex-col gap-1">
      <span class="text-sm font-semibold text-slate-600">Proportions</span>
      <div class="flex flex-row flex-wrap gap-2">
        {#each aspectRatios.value as aspectRatio, idx}
          <Button active={idx == ratioIdx} onclick={() => selectRatio(idx)}>
            {#if idx < 9}
              <span class="font-semibold text-slate-500">{idx + 1}</span>
            {/if}
            {aspectRatio.label}
          </Button>
        {/each}
      </div>
    </div>

    <label class="flex flex-row items-center gap-3 text-sm text-slate-600">
      Size of new crops
      <input type="range" min="0.1" max="1" step="0.05" bind:value={sizeFraction} class="flex-1" />
      <span class="w-12 text-right">{Math.round(sizeFraction * 100)}%</span>
    </label>

    <p class="text-xs text-slate-500">
      {#if ratio}
        Click the image to create a crop centered there, or drag to draw one.
      {:else}
        Drag on the image to draw a crop.
      {/if}
      Drag a crop to move it, its handles to resize it, or scroll over it to scale it.
    </p>

    {#if error}
      <div class="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-1.5 whitespace-pre-wrap">{error}</div>
    {/if}

    <span class="text-sm font-semibold text-slate-600">Crops ({crops.value.length})</span>

    <div class="flex flex-col gap-2">
      {#each crops.value as crop (crop.path)}
        <div
          class={[
            "flex flex-row items-center gap-3 p-1.5 rounded-lg ring-1 cursor-pointer",
            crop.path == selected ? "ring-cyan-400 bg-cyan-50" : "ring-gray-200 hover:bg-gray-50",
          ]}
          role="button"
          tabindex="-1"
          onclick={() => { selected = crop.path; }}
          onkeydown={() => {}}
        >
          <Thumbnail {loader} path={crop.path} imageKey={crop.key} size={56} />
          <div class="flex-1 min-w-0 flex flex-col text-sm">
            <span class="text-slate-800">{describe(crop.box)}</span>
            <span class="text-xs text-slate-500 truncate" title={crop.path}>{crop.path.split(/[\\/]/).pop()}</span>
          </div>
          {#if crop.locked}
            <span title="Has derived images of its own, so it can't be changed">
              <IconLock class="w-4 h-4 text-slate-400" />
            </span>
          {:else}
            <Button
              size="sm"
              variant={confirmDelete.pending == crop.path ? "confirm-danger" : "danger"}
              icon={IconTrash}
              onclick={(event) => { event.stopPropagation(); deleteCrop(crop.path); }}
            >
              {confirmDelete.pending == crop.path ? "Sure?" : "Delete"}
            </Button>
          {/if}
        </div>
      {:else}
        <span class="text-sm text-gray-400">None yet</span>
      {/each}
    </div>
  {/snippet}
</Viewer>
