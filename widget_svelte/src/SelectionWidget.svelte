<script lang="ts">
  import IconCircleCheck from "@lucide/svelte/icons/circle-check";
  import IconCircleX from "@lucide/svelte/icons/circle-x";
  import IconRotateCCW from "@lucide/svelte/icons/rotate-ccw";
  import { onDestroy, untrack } from "svelte";
  import type { WidgetProps } from "./anywidget.svelte";
  import { useTrait, sendMessage } from "./anywidget.svelte";
  import { ImageLoader } from "./imageLoader";
  import type { Shortcut } from "./hotkeys";
  import type { ViewerTraits } from "./types";
  import Viewer from "./Viewer.svelte";
  import Toggle from "./Toggle.svelte";

  type Traits = ViewerTraits & {
    choice: boolean | null;
    default_choice: boolean;
    auto_advance: boolean;
  };

  // These mustn't ever change, so we get rid of reactivity here.
  let _props: WidgetProps<Traits> = $props();
  let { model, experimental } = untrack(() => _props);

  const loader = new ImageLoader(experimental);
  onDestroy(() => loader.dispose());

  const choice = useTrait(model, "choice");
  const defaultChoice = useTrait(model, "default_choice");
  const autoAdvance = useTrait(model, "auto_advance");

  let effective = $derived(choice.value ?? defaultChoice.value);

  function setChoice(value: boolean | null) {
    sendMessage(model, "set_choice", { choice: value });
  }

  // S/D are next to each other on the home row, so they're easy to reach with the left hand
  // while the right one navigates with the arrows. Y/N are kept as mnemonic alternatives.
  const shortcuts: Shortcut[] = [
    { code: "KeyS", callback: () => setChoice(true) },
    { code: "KeyY", callback: () => setChoice(true) },
    { code: "KeyD", callback: () => setChoice(false) },
    { code: "KeyN", callback: () => setChoice(false) },
    { code: "KeyA", callback: () => setChoice(null) },
    { code: "Backspace", callback: () => setChoice(null) },
  ];
</script>

<Viewer
  {model}
  {loader}
  {shortcuts}
  help={[
    { keys: [["S"], ["Y"]], text: "select" },
    { keys: [["D"], ["N"]], text: "reject" },
    { keys: [["A"], ["Backspace"]], text: "reset to default" },
]}
>
  {#snippet side()}
    <div class="flex flex-row gap-3">
      <button
        class={[
          "choice-btn",
          choice.value === true ? "bg-green-600 text-white ring-green-700" : "bg-green-50 text-green-800 ring-green-300 hover:bg-green-100",
        ]}
        onclick={() => setChoice(true)}
      >
        <IconCircleCheck class="w-6 h-6" />
        Select
        <kbd class="choice-kbd">S</kbd>
</button>
      <button
        class={[
          "choice-btn",
          choice.value === false ? "bg-red-600 text-white ring-red-700" : "bg-red-50 text-red-800 ring-red-300 hover:bg-red-100",
        ]}
        onclick={() => setChoice(false)}
      >
        <IconCircleX class="w-6 h-6" />
        Reject
        <kbd class="choice-kbd">D</kbd>
</button>
    </div>

    <div class="flex flex-row items-center gap-3 text-sm text-slate-600">
      <span>
        Currently <b class={effective ? "text-green-700" : "text-red-700"}>{effective ? "selected" : "rejected"}</b>
        {#if choice.value === null}(by default){/if}
      </span>
      {#if choice.value !== null}
        <button class="flex items-center gap-1 text-slate-500 hover:text-slate-800" onclick={() => setChoice(null)}>
          <IconRotateCCW class="w-4 h-4" />
          Reset to default
        </button>
      {/if}
    </div>

    <Toggle size="sm" class="text-sm text-slate-600" bind:checked={autoAdvance.value}>
      Advance to the next image after choosing
    </Toggle>
{/snippet}
</Viewer>

<style lang="postcss">
  @reference "./app.css";

  .choice-btn {
    @apply flex-1 flex flex-row items-center justify-center gap-2 py-4 rounded-lg ring-1 text-lg font-semibold transition-colors duration-100;
  }

  .choice-kbd {
    @apply ml-1 px-1.5 text-xs font-semibold rounded-md ring-1 ring-current/30 opacity-70;
  }
</style>
