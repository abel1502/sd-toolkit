<script lang="ts">
  import IconRotateCCW from "@lucide/svelte/icons/rotate-ccw";
  import { onDestroy, untrack } from "svelte";
  import type { WidgetProps } from "./anywidget.svelte";
  import { useTrait, sendMessage } from "./anywidget.svelte";
  import { ImageLoader } from "./imageLoader";
  import { hotkeyCode, type Shortcut } from "./hotkeys";
  import type { TagDisplay, ViewerTraits } from "./types";
  import TagList from "./TagList.svelte";
  import TagInput from "./TagInput.svelte";
  import Viewer from "./Viewer.svelte";
  import Button from "./Button.svelte";

  type Traits = ViewerTraits & {
    tags: TagDisplay[];
    vocabulary: string[];
    actions: { label: string, hotkey: string | null }[];
    error: string;
  };

  // These mustn't ever change, so we get rid of reactivity here.
  let _props: WidgetProps<Traits> = $props();
  let { model, experimental } = untrack(() => _props);

  const loader = new ImageLoader(experimental);
  onDestroy(() => loader.dispose());

  const tags = useTrait(model, "tags");
  const vocabulary = useTrait(model, "vocabulary");
  const actions = useTrait(model, "actions");
  const error = useTrait(model, "error");

  let presentTags = $derived(new Set(tags.value.map(tag => tag.path_str)));

  let input: HTMLInputElement | undefined = $state();

  function addTags(text: string) {
    sendMessage(model, "add_tags", { text });
  }

  function removeTag(tag: TagDisplay) {
    sendMessage(model, "remove_tag", { path: tag.path });
  }

  function runAction(idx: number) {
    sendMessage(model, "run_action", { idx });
  }

  function revertImage() {
    sendMessage(model, "revert_image");
  }

  let shortcuts: Shortcut[] = $derived([
    ...actions.value.flatMap((action, idx) => action.hotkey ? [{
      code: hotkeyCode(action.hotkey),
      callback: () => runAction(idx),
    }] : []),
    { code: "Slash", callback: () => input?.focus() },
    { code: "Backspace", callback: revertImage },
  ]);
</script>

<Viewer
  {model}
  {experimental}
  {loader}
  {shortcuts}
  help={[
    ...(actions.value.some(action => action.hotkey) ? [{ keys: [["action hotkey"]], text: "run action" }] : []),
    { keys: [["/"]], text: "add tags" },
    { keys: [["Esc"]], text: "leave the input" },
    { keys: [["Backspace"]], text: "reset current image" },
  ]}
  imageButtons={[
    {
      icon: IconRotateCCW,
      title: "Reset image tags",
      onclick: revertImage,
    },
  ]}
>
  {#snippet side()}
    <TagInput vocabulary={vocabulary.value} present={presentTags} onsubmit={addTags} bind:input />

    {#if error.value}
      <div class="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-1.5 whitespace-pre-wrap">{error.value}</div>
    {/if}

    {#if actions.value.length > 0}
      <div class="flex flex-row flex-wrap gap-2">
        {#each actions.value as action, idx}
          <Button onclick={() => runAction(idx)}>
            {#if action.hotkey}
              <span class="font-semibold text-slate-500">{action.hotkey}</span>
            {/if}
            {action.label}
          </Button>
        {/each}
      </div>
    {/if}

    <TagList tags={tags.value} onremove={removeTag} />
  {/snippet}
</Viewer>
