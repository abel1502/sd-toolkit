<script lang="ts">
  import type { Snippet } from "svelte";
  import { untrack } from "svelte";
  import { Confetti } from "svelte-confetti";
  import { slide } from "svelte/transition";
  import IconZoomIn from "@lucide/svelte/icons/zoom-in";
  import IconInfo from "@lucide/svelte/icons/info";
  import IconImagePlus from "@lucide/svelte/icons/image-plus";

  import type { AnyModel, Experimental } from "./anywidget.svelte";
  import { useTrait, sendMessage, invoke } from "./anywidget.svelte";
  import { Notifier } from "./notifier.svelte";
  import type { ImageLoader } from "./imageLoader";
  import type { Shortcut, ShortcutHelp } from "./hotkeys";
  import type { ImageButton, SwitchImageEvent, ViewerImage, ViewerTraits } from "./types";
  import NavBar from "./NavBar.svelte";
  import HotkeyBar from "./HotkeyBar.svelte";
  import ImagePreview from "./ImagePreview.svelte";
  import InfoPanel from "./InfoPanel.svelte";

  interface Props {
    model: AnyModel<ViewerTraits>;
    experimental: Experimental;
    loader: ImageLoader;
    /** Shows status messages over the image. Pass one to show messages from the widget too. */
    notifier?: Notifier;
    /** The panel to the right of the image. */
    side: Snippet;
    /** Replaces the plain image (e.g. to draw on top of it). */
    imageContent?: Snippet<[ViewerImage]>;
    imageButtons?: ImageButton[];
    shortcuts?: Shortcut[];
    help?: ShortcutHelp[];
    /** Awaited before switching to another image. */
    beforeNavigate?: () => Promise<void> | void;
    showInfo?: boolean;
    /** Classes for the main area (the image and the side panel), e.g. to change its height. */
    areaClass?: string;
  };

  let {
    model,
    experimental,
    loader,
    notifier = new Notifier(),
    side,
    imageContent,
    imageButtons = [],
    shortcuts = [],
    help = [],
    beforeNavigate,
    showInfo = $bindable(false),
    areaClass = "h-72",
  }: Props = $props();

  // The model mustn't ever change, so we get rid of reactivity here.
  const _model = untrack(() => model);

  const imageIdx = useTrait(_model, "image_idx");
  const imageCount = useTrait(_model, "image_count");
  const imageKey = useTrait(_model, "image_key");
  const imagePath = useTrait(_model, "image_path");
  const imageInfo = useTrait(_model, "image_info");
  const imageMarks = useTrait(_model, "image_marks");
  const markStyles = useTrait(_model, "mark_styles");
  const hasDoneScreen = useTrait(_model, "has_done_screen");
  const canEditCopy = useTrait(_model, "can_edit_copy");

  let maxIdx = $derived(hasDoneScreen.value ? imageCount.value : Math.max(0, imageCount.value - 1));
  let isDone = $derived(hasDoneScreen.value && imageIdx.value >= imageCount.value);
  let badge = $derived(markStyles.value[imageMarks.value[imageIdx.value] ?? 0] ?? null);

  let imageUrl: string | null = $state(null);
  let loadedKey: string = $state("");
  let loading: boolean = $state(false);
  let error: string | null = $state(null);

  $effect(() => {
    const idx = imageIdx.value;
    const key = imageKey.value;
    const count = imageCount.value;

    if (!key) {
      imageUrl = null;
      loadedKey = "";
      loading = false;
      error = imagePath.value ? `Cannot find ${imagePath.value}` : null;
      return;
    }

    let cancelled = false;
    loading = true;

    loader.load({ idx }, key).then(
      (result) => {
        if (cancelled) return;
        imageUrl = result.url;
        loadedKey = result.key;
        loading = false;
        error = null;
      },
      (e) => {
        if (cancelled) return;
        imageUrl = null;
        loadedKey = "";
        loading = false;
        error = String(e);
      },
    );

    for (const delta of [1, -1, 2]) {
      if (idx + delta >= 0 && idx + delta < count) {
        loader.prefetch({ idx: idx + delta });
      }
    }

    return () => { cancelled = true; };
  });

  async function goToImage(event: SwitchImageEvent) {
    const idx = Math.max(0, Math.min(event.idx, maxIdx));

    await beforeNavigate?.();

    // TODO: Toggle a spinner until image changes?
    sendMessage(_model, "switch_image", { idx });
  }

  function nextImage() {
    goToImage({ idx: imageIdx.value + 1 });
  }

  function prevImage() {
    goToImage({ idx: imageIdx.value - 1 });
  }

  let allButtons: ImageButton[] = $derived([
    ...imageButtons,
    ...(canEditCopy.value ? [{
      icon: IconImagePlus,
      title: "Create an edited copy",
      onclick: () => notifier.track(
        invoke(experimental, "edit_copy", {}),
        "Creating an edited copy...",
        "Opened the copy in the image editor",
      ),
    }] : []),
    {
      icon: IconInfo,
      title: (showInfo ? "Hide" : "Show") + " image info",
      onclick: () => { showInfo = !showInfo; },
    },
    {
      icon: IconZoomIn,
      title: "Open in external viewer",
      onclick: () => notifier.track(
        invoke(experimental, "view_image", {}),
        "Opening in the image viewer...",
        "Opened in the image viewer",
      ),
    },
  ]);

  let allShortcuts: Shortcut[] = $derived([
    ...shortcuts,
    { code: "Space", callback: nextImage },
    { code: "ArrowRight", callback: nextImage },
    { code: "Space", modifiers: ["shift"], callback: prevImage },
    { code: "ArrowLeft", callback: prevImage },
  ]);

  let allHelp: ShortcutHelp[] = $derived([
    { keys: [["Space"], ["→"]], text: "next image" },
    { keys: [["Shift", "Space"], ["←"]], text: "previous image" },
    ...help,
  ]);

  let width: number = $state(0);
</script>


<div class="flex flex-col w-full resize-x min-w-2xl max-w-full p-4 border rounded-lg bg-white shadow-sm overflow-hidden text-black" bind:clientWidth={width}>
  {#if isDone}
    <div class="grid place-items-center h-16 border border-green-300 p-4 rounded-lg bg-green-200 shadow-sm">
      {#if imageCount.value > 0}
        <Confetti x={[-width / 400.0, width / 400.0]} y={[-0.5, 0.25]} amount={100} />
      {/if}
      <span class="text-green-800 font-bold absolute">Done!</span>
    </div>
  {:else if imageCount.value == 0}
    <div class="grid place-items-center h-16 border border-gray-300 p-4 rounded-lg bg-gray-100 text-gray-500">
      The dataset is empty
    </div>
  {:else}
    <div class={["flex flex-row gap-6 resize-y min-h-48 overflow-hidden", areaClass]} transition:slide>
      <ImagePreview
        class="h-full max-h-[35vw] shrink-0"
        url={imageUrl}
        {loading}
        {error}
        {badge}
        buttons={allButtons}
        notice={notifier.current}
        content={imageContent && (imageUrl || loading) ? imageContentSnippet : undefined}
      />

      <!-- Padded, so that the outlines (rings) of the elements at the edges aren't clipped -->
      <div class="flex-1 min-w-0 p-1 overflow-y-auto scrollbar-hidden flex flex-col gap-3">
        {#if showInfo}
          <InfoPanel items={imageInfo.value} />
        {/if}
        {@render side()}
      </div>
    </div>
  {/if}

  <NavBar
    class="mt-6"
    curImageIdx={imageIdx.value}
    totalImages={imageCount.value}
    {maxIdx}
    marks={imageMarks.value}
    markStyles={markStyles.value}
    {goToImage}
    {nextImage}
    {prevImage}
  />

  <HotkeyBar class="mt-4" shortcuts={allShortcuts} help={allHelp} />
</div>

{#snippet imageContentSnippet()}
  {@render imageContent!({ idx: imageIdx.value, url: imageUrl, key: loadedKey })}
{/snippet}
