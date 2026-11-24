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

  const shortcuts: Shortcut[] = [
    { code: "KeyY", callback: () => setChoice(true) },
    { code: "Digit1", callback: () => setChoice(true) },
    { code: "KeyN", callback: () => setChoice(false) },
    { code: "Digit0", callback: () => setChoice(false) },
    { code: "Backspace", callback: () => setChoice(null) },
  ];
</script>

<Viewer
  {model}
  {loader}
  {shortcuts}
  help={[
    { keys: [["Y"], ["1"]], text: "select" },
    { keys: [["N"], ["0"]], text: "reject" },
    { keys: [["Backspace"]], text: "reset to default" },
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

    <label class="flex items-center gap-2 text-sm text-slate-600 cursor-pointer select-none">
      <input
        type="checkbox"
        checked={autoAdvance.value}
        onchange={(event) => { autoAdvance.value = event.currentTarget.checked; }}
      />
      Advance to the next image after choosing
    </label>
  {/snippet}
</Viewer>

<style lang="postcss">
  @reference "./app.css";

  .choice-btn {
    @apply flex-1 flex flex-row items-center justify-center gap-2 py-4 rounded-lg ring-1 text-lg font-semibold transition-colors duration-100;
  }
</style>
