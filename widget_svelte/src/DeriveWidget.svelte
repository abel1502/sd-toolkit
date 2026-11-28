<script lang="ts">
  import IconImagePlus from "@lucide/svelte/icons/image-plus";
  import IconPencilLine from "@lucide/svelte/icons/pencil-line";
  import IconTrash from "@lucide/svelte/icons/trash-2";
  import IconRefresh from "@lucide/svelte/icons/refresh-cw";
  import { onDestroy, untrack } from "svelte";
  import type { WidgetProps } from "./anywidget.svelte";
  import { useTrait, sendMessage, invoke } from "./anywidget.svelte";
  import { Notifier, ActionStatus } from "./notifier.svelte";
  import { ImageLoader } from "./imageLoader";
  import type { Shortcut } from "./hotkeys";
  import type { ViewerTraits } from "./types";
  import { TwoStepConfirm, throttled } from "./confirm.svelte";
  import Viewer from "./Viewer.svelte";
  import Thumbnail from "./Thumbnail.svelte";
  import Button from "./Button.svelte";

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

  const notifier = new Notifier();
  const editStatus = new ActionStatus(notifier);
  const openStatus = new ActionStatus(notifier);
  /** The child that `openStatus` is about. */
  let opening: string | null = $state(null);

  function editCopy() {
    editStatus.run(invoke(experimental, "edit_copy", {}));
  }

  function openDerived(child: DerivedImageInfo) {
    opening = child.path;
    openStatus.run(invoke(experimental, "open_derived", { path: child.path }));
  }

  const confirmDelete = new TwoStepConfirm<string>();

  function deleteDerived(child: DerivedImageInfo) {
    if (confirmDelete.request(child.path)) {
      sendMessage(model, "delete_derived", { path: child.path });
    }
  }

  function refresh() {
    sendMessage(model, "refresh");
  }

  // The derived images were probably edited in another app, so refresh when the user comes back
  const onfocus = throttled(refresh);

  const shortcuts: Shortcut[] = [
    { code: "KeyE", callback: editCopy },
    { code: "KeyR", callback: refresh },
  ];
</script>

<svelte:window {onfocus} />

<Viewer
  {model}
  {experimental}
  {loader}
  {notifier}
  {shortcuts}
  help={[
    { keys: [["E"]], text: "create an edited copy" },
    { keys: [["R"]], text: "refresh" },
  ]}
>
  {#snippet side()}
    <div class="flex flex-row flex-wrap items-center gap-2">
      <Button variant="primary" icon={IconImagePlus} status={editStatus.state} onclick={editCopy}>Create an edited copy</Button>
      <Button
        icon={IconRefresh}
        onclick={refresh}
        title="Reload the previews (happens automatically when the window regains focus)"
      >
        Refresh
      </Button>
</div>

    <span class="text-sm font-semibold text-slate-600">New images ({children.value.length})</span>

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
            <Button
              size="sm"
              class="flex-1"
              icon={IconPencilLine}
              status={opening == child.path ? openStatus.state : "idle"}
              onclick={() => openDerived(child)}
            >
              Edit
            </Button>
            <Button
              size="sm"
              class="flex-1"
              variant={confirmDelete.pending == child.path ? "confirm-danger" : "danger"}
              icon={IconTrash}
              onclick={() => deleteDerived(child)}
            >
              {confirmDelete.pending == child.path ? "Sure?" : "Delete"}
            </Button>
          </div>
</div>
      {:else}
        <span class="text-sm text-gray-400">None yet</span>
      {/each}
    </div>
  {/snippet}
</Viewer>
