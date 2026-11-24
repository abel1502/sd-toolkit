<script lang="ts">
  import IconImagePlus from "@lucide/svelte/icons/image-plus";
  import IconPencilLine from "@lucide/svelte/icons/pencil-line";
  import IconTrash from "@lucide/svelte/icons/trash-2";
  import IconRefresh from "@lucide/svelte/icons/refresh-cw";
  import { onDestroy, untrack } from "svelte";
  import type { WidgetProps } from "./anywidget.svelte";
  import { useTrait, sendMessage } from "./anywidget.svelte";
  import { ImageLoader } from "./imageLoader";
  import type { Shortcut } from "./hotkeys";
  import type { ViewerTraits } from "./types";
  import Viewer from "./Viewer.svelte";
  import Thumbnail from "./Thumbnail.svelte";

  interface DerivedImageInfo {
    path: string;
    name: string;
    kind: string;
    key: string;
  };

  type Traits = ViewerTraits & {
    children: DerivedImageInfo[];
  };

  // These mustn't ever change, so we get rid of reactivity here.
  let _props: WidgetProps<Traits> = $props();
  let { model, experimental } = untrack(() => _props);

  const loader = new ImageLoader(experimental, { maxEntries: 64 });
  onDestroy(() => loader.dispose());

  const children = useTrait(model, "children");

  function editCopy() {
    sendMessage(model, "edit_copy");
  }

  function openDerived(child: DerivedImageInfo) {
    sendMessage(model, "open_derived", { path: child.path });
  }

  // Deletion requires a second click to confirm
  let confirmingDelete: string | null = $state(null);
  let confirmTimeout: ReturnType<typeof setTimeout> | undefined;

  function deleteDerived(child: DerivedImageInfo) {
    clearTimeout(confirmTimeout);

    if (confirmingDelete != child.path) {
      confirmingDelete = child.path;
      confirmTimeout = setTimeout(() => { confirmingDelete = null; }, 3000);
      return;
    }

    confirmingDelete = null;
    sendMessage(model, "delete_derived", { path: child.path });
  }

  function refresh() {
    sendMessage(model, "refresh");
  }

  // The derived images were probably edited in another app, so refresh when the user comes back
  let lastRefresh = 0;
  function onfocus() {
    if (Date.now() - lastRefresh < 1000) return;
    lastRefresh = Date.now();
    refresh();
  }

  const shortcuts: Shortcut[] = [
    { code: "KeyE", callback: editCopy },
    { code: "KeyR", callback: refresh },
  ];
</script>

<svelte:window {onfocus} />

<Viewer
  {model}
  {loader}
  {shortcuts}
  help={[
    { keys: [["E"]], text: "create an edited copy" },
    { keys: [["R"]], text: "refresh" },
  ]}
>
  {#snippet side()}
    <div class="flex flex-row flex-wrap items-center gap-2">
      <button
        class="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg ring-1 ring-blue-300 bg-blue-50 text-blue-800 hover:bg-blue-100"
        onclick={editCopy}
      >
        <IconImagePlus class="w-4 h-4" />
        Create an edited copy
      </button>
      <button
        class="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg ring-1 ring-gray-300 bg-gray-50 text-gray-700 hover:bg-gray-100"
        onclick={refresh}
        title="Reload the previews (happens automatically when the window regains focus)"
      >
        <IconRefresh class="w-4 h-4" />
        Refresh
      </button>
    </div>

    <span class="text-sm font-semibold text-slate-600">Derived images ({children.value.length})</span>

    <div class="flex flex-row flex-wrap gap-3">
      {#each children.value as child (child.path)}
        <div class="flex flex-col gap-1 w-40">
          {#if child.key}
            <Thumbnail {loader} path={child.path} imageKey={child.key} />
          {:else}
            <div class="w-40 h-40 grid place-items-center text-xs text-red-500 bg-gray-100 rounded-md border border-gray-300">Missing</div>
          {/if}
          <span class="text-xs text-slate-600 truncate" title={child.path}>
            <b>{child.kind}</b> {child.name}
          </span>
          <div class="flex flex-row gap-1">
            <button
              class="flex-1 flex items-center justify-center gap-1 py-1 text-xs rounded-md ring-1 ring-gray-300 bg-gray-50 text-gray-700 hover:bg-gray-100"
              onclick={() => openDerived(child)}
            >
              <IconPencilLine class="w-3.5 h-3.5" /> Edit
            </button>
            <button
              class={[
                "flex-1 flex items-center justify-center gap-1 py-1 text-xs rounded-md ring-1",
                confirmingDelete == child.path
                  ? "ring-red-400 bg-red-600 text-white"
                  : "ring-gray-300 bg-gray-50 text-gray-700 hover:bg-red-50 hover:text-red-700",
              ]}
              onclick={() => deleteDerived(child)}
            >
              <IconTrash class="w-3.5 h-3.5" /> {confirmingDelete == child.path ? "Sure?" : "Delete"}
            </button>
          </div>
        </div>
      {:else}
        <span class="text-sm text-gray-400">None yet</span>
      {/each}
    </div>
  {/snippet}
</Viewer>
