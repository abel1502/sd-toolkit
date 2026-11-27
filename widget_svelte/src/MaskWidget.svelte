<script lang="ts">
  import IconBrush from "@lucide/svelte/icons/brush";
  import IconEraser from "@lucide/svelte/icons/eraser";
  import IconUndo from "@lucide/svelte/icons/undo-2";
  import IconTrash from "@lucide/svelte/icons/trash-2";
  import IconContrast from "@lucide/svelte/icons/contrast";
  import IconSave from "@lucide/svelte/icons/save";
  import IconCircleSlash from "@lucide/svelte/icons/circle-slash";
  import IconExternalLink from "@lucide/svelte/icons/external-link";
import { onDestroy, untrack } from "svelte";
  import type { WidgetProps } from "./anywidget.svelte";
  import { useTrait, sendMessage, invoke } from "./anywidget.svelte";
  import { ImageLoader } from "./imageLoader";
  import type { Shortcut } from "./hotkeys";
  import type { ViewerTraits } from "./types";
  import { throttled } from "./confirm.svelte";
  import { Notifier } from "./notifier.svelte";
  import Viewer from "./Viewer.svelte";
  import Button from "./Button.svelte";
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

  async function editExternally() {
    if (dirty) {
      await save();
    }
    notifier.track(
      invoke(experimental, "edit_externally", {}),
      "Opening the mask in the image editor...",
      "Opened in the image editor. Changes are imported when you come back here",
    );
  }

  const notifier = new Notifier();

  // The mask might have been edited externally, so check for changes when the user comes back
  const onfocus = throttled(() => sendMessage(model, "import_external"));

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
    { code: "KeyK", callback: () => { editExternally(); } },
  ];
</script>

<svelte:window {onfocus} />

<Viewer
  {model}
  {experimental}
  {loader}
  {notifier}
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
    { keys: [["K"]], text: "edit in the external editor" },
]}
>
  {#snippet imageContent(image)}
    {#if image.url && image.key == imageKey.value && maskUrl !== undefined && maskUrlFor == imageKey.value}
      <MaskCanvas bind:this={maskCanvas} bind:dirty imageUrl={image.url} {maskUrl} {mode} {brushSize} />
    {/if}
  {/snippet}

  {#snippet side()}
    <div class="flex flex-row gap-2">
      <Button icon={IconBrush} active={mode == "brush"} onclick={() => { mode = "brush"; }}>Brush</Button>
      <Button icon={IconEraser} active={mode == "eraser"} onclick={() => { mode = "eraser"; }}>Eraser</Button>
    </div>

    <label class="flex flex-row items-center gap-3 text-sm text-slate-600">
      Size
      <input type="range" min="2" max="400" bind:value={brushSize} class="flex-1" />
      <span class="w-12 text-right">{brushSize}px</span>
    </label>

    <div class="flex flex-row flex-wrap gap-2">
      <Button icon={IconUndo} onclick={() => maskCanvas?.undo()}>Undo</Button>
      <Button icon={IconContrast} onclick={() => maskCanvas?.invert()}>Invert</Button>
      <Button icon={IconCircleSlash} onclick={() => maskCanvas?.clear()}>Clear</Button>
    </div>

    <div class="flex flex-row flex-wrap items-center gap-2">
      <Button icon={IconSave} active={dirty} disabled={!dirty || saving} onclick={() => save()}>
        {saving ? "Saving..." : "Save"}
      </Button>
      {#if maskKey.value}
        <Button variant="danger" icon={IconTrash} onclick={deleteMask}>Delete saved mask</Button>
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

    <div class="flex flex-row flex-wrap items-center gap-2">
      <Button
        icon={IconExternalLink}
        onclick={editExternally}
        title="Open the image and the mask as layers in the external editor (e.g. Krita). Saved changes are imported when you come back."
      >
        Edit in external editor
      </Button>
    </div>

    {#if saveError}
      <div class="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-1.5">{saveError}</div>
    {/if}
  {/snippet}
</Viewer>

