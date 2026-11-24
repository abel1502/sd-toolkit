<script lang="ts">
  import IconBrush from "@lucide/svelte/icons/brush";
  import IconEraser from "@lucide/svelte/icons/eraser";
  import IconUndo from "@lucide/svelte/icons/undo-2";
  import IconTrash from "@lucide/svelte/icons/trash-2";
  import IconContrast from "@lucide/svelte/icons/contrast";
  import IconSave from "@lucide/svelte/icons/save";
  import IconCircleSlash from "@lucide/svelte/icons/circle-slash";
  import { onDestroy, untrack } from "svelte";
  import type { WidgetProps } from "./anywidget.svelte";
  import { useTrait, sendMessage, invoke } from "./anywidget.svelte";
  import { ImageLoader } from "./imageLoader";
  import type { Shortcut } from "./hotkeys";
  import type { ViewerTraits } from "./types";
  import Viewer from "./Viewer.svelte";
  import MaskCanvas, { type BrushMode } from "./MaskCanvas.svelte";

  type Traits = ViewerTraits & {
    mask_path: string;
    mask_key: string;
  };

  // These mustn't ever change, so we get rid of reactivity here.
  let _props: WidgetProps<Traits> = $props();
  let { model, experimental } = untrack(() => _props);

  const loader = new ImageLoader(experimental);
  onDestroy(() => loader.dispose());

  const imageIdx = useTrait(model, "image_idx");
  const imageKey = useTrait(model, "image_key");
  const maskPath = useTrait(model, "mask_path");
  const maskKey = useTrait(model, "mask_key");

  let mode: BrushMode = $state("brush");
  let brushSize: number = $state(40);
  let dirty: boolean = $state(false);
  let saving: boolean = $state(false);
  let saveError: string | null = $state(null);
  let maskCanvas: MaskCanvas | undefined = $state();

  // The saved mask of the current image: `undefined` while loading
  let maskUrl: string | null | undefined = $state(undefined);
  let maskUrlFor: string = $state("");

  $effect(() => {
    const path = maskPath.value;
    const key = maskKey.value;
    const forImage = imageKey.value;
    let cancelled = false;

    if (!key) {
      maskUrl = null;
      maskUrlFor = forImage;
      return;
    }

    maskUrl = undefined;
    loader.load({ path }, key).then(
      (result) => {
        if (cancelled) return;
        maskUrl = result.url;
        maskUrlFor = forImage;
      },
      (e) => {
        if (cancelled) return;
        saveError = `Failed to load the saved mask: ${e}`;
        maskUrl = null;
        maskUrlFor = forImage;
      },
    );

    return () => { cancelled = true; };
  });

  async function save() {
    if (!maskCanvas || saving) return;

    saving = true;
    saveError = null;

    try {
      const blob = await maskCanvas.exportMask();

      if (blob === null) {
        if (maskKey.value) {
          sendMessage(model, "delete_mask");
        }
      } else {
        const buffer = new DataView(await blob.arrayBuffer());
        await invoke(experimental, "save_mask", { idx: imageIdx.value }, [buffer]);
      }
    } catch (e) {
      saveError = String(e);
      throw e;
    } finally {
      saving = false;
    }
  }

  async function beforeNavigate() {
    // Changes are saved automatically when switching images
    if (dirty) {
      await save();
    }
  }

  function deleteMask() {
    sendMessage(model, "delete_mask");
  }

  function changeBrushSize(factor: number) {
    brushSize = Math.round(Math.max(2, Math.min(400, brushSize * factor)));
  }

  const shortcuts: Shortcut[] = [
    { code: "KeyB", callback: () => { mode = "brush"; } },
    { code: "KeyE", callback: () => { mode = "eraser"; } },
    { code: "BracketLeft", callback: () => changeBrushSize(1 / 1.2), repeat: true },
    { code: "BracketRight", callback: () => changeBrushSize(1.2), repeat: true },
    { code: "KeyZ", modifiers: ["ctrl"], callback: () => maskCanvas?.undo(), repeat: true },
    { code: "KeyS", modifiers: ["ctrl"], callback: () => { save(); } },
    { code: "KeyI", callback: () => maskCanvas?.invert() },
    { code: "Delete", callback: () => maskCanvas?.clear() },
  ];
</script>

<Viewer
  {model}
  {loader}
  {shortcuts}
  {beforeNavigate}
  areaClass="h-[36rem]"
  help={[
    { keys: [["B"]], text: "brush" },
    { keys: [["E"]], text: "eraser" },
    { keys: [["["], ["]"]], text: "brush size" },
    { keys: [["Ctrl", "Z"]], text: "undo" },
    { keys: [["Ctrl", "S"]], text: "save (also happens when switching images)" },
    { keys: [["I"]], text: "invert" },
    { keys: [["Del"]], text: "clear" },
  ]}
>
  {#snippet imageContent(image)}
    {#if image.url && image.key == imageKey.value && maskUrl !== undefined && maskUrlFor == imageKey.value}
      <MaskCanvas bind:this={maskCanvas} bind:dirty imageUrl={image.url} {maskUrl} {mode} {brushSize} />
    {/if}
  {/snippet}

  {#snippet side()}
    <div class="flex flex-row gap-2">
      <button class={["tool-btn", mode == "brush" ? "tool-btn--on" : "tool-btn--off"]} onclick={() => { mode = "brush"; }}>
        <IconBrush class="w-4 h-4" /> Brush
      </button>
      <button class={["tool-btn", mode == "eraser" ? "tool-btn--on" : "tool-btn--off"]} onclick={() => { mode = "eraser"; }}>
        <IconEraser class="w-4 h-4" /> Eraser
      </button>
    </div>

    <label class="flex flex-row items-center gap-3 text-sm text-slate-600">
      Size
      <input type="range" min="2" max="400" bind:value={brushSize} class="flex-1" />
      <span class="w-12 text-right">{brushSize}px</span>
    </label>

    <div class="flex flex-row flex-wrap gap-2">
      <button class="tool-btn tool-btn--off" onclick={() => maskCanvas?.undo()}>
        <IconUndo class="w-4 h-4" /> Undo
      </button>
      <button class="tool-btn tool-btn--off" onclick={() => maskCanvas?.invert()}>
        <IconContrast class="w-4 h-4" /> Invert
      </button>
      <button class="tool-btn tool-btn--off" onclick={() => maskCanvas?.clear()}>
        <IconCircleSlash class="w-4 h-4" /> Clear
      </button>
    </div>

    <div class="flex flex-row flex-wrap items-center gap-2">
      <button
        class={["tool-btn", dirty ? "tool-btn--on" : "tool-btn--off"]}
        disabled={!dirty || saving}
        onclick={() => save()}
      >
        <IconSave class="w-4 h-4" /> {saving ? "Saving..." : "Save"}
      </button>
      {#if maskKey.value}
        <button class="tool-btn tool-btn--off hover:text-red-700" onclick={deleteMask}>
          <IconTrash class="w-4 h-4" /> Delete saved mask
        </button>
      {/if}
      <span class="text-sm text-slate-500">
        {#if dirty}
          Unsaved changes
        {:else if maskKey.value}
          Saved
        {:else}
          No mask
        {/if}
      </span>
    </div>

    {#if saveError}
      <div class="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-1.5">{saveError}</div>
    {/if}
  {/snippet}
</Viewer>

<style lang="postcss">
  @reference "./app.css";

  .tool-btn {
    @apply flex flex-row items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg ring-1 disabled:opacity-50 transition-colors duration-100;
  }

  .tool-btn--on {
    @apply bg-blue-100 text-blue-800 ring-blue-300 not-disabled:hover:bg-blue-50;
  }

  .tool-btn--off {
    @apply bg-gray-50 text-gray-700 ring-gray-300 not-disabled:hover:bg-gray-100;
  }
</style>
