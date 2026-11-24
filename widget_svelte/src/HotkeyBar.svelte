<script lang="ts">
  import { onDestroy } from "svelte";

  import { enabledHotkeys, dispatchShortcut, type Shortcut, type ShortcutHelp } from "./hotkeys";

  interface Props {
    shortcuts: Shortcut[];
    help: ShortcutHelp[];
    class?: string;
  };

  let { shortcuts, help, class: extraClass = "" }: Props = $props();

  // Identifies this widget in the global hotkeys state.
  const hotkeyScope = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

  let hotkeysEnabled = $derived($enabledHotkeys === hotkeyScope);

  function releaseHotkeys() {
    enabledHotkeys.update(scope => scope === hotkeyScope ? null : scope);
  }

  function updateHotkeysEnabled(enabled: boolean) {
    if (enabled) {
      enabledHotkeys.set(hotkeyScope);
    } else {
      releaseHotkeys();
    }
  }

  onDestroy(releaseHotkeys);

  function onkeydown(event: KeyboardEvent) {
    if (!hotkeysEnabled) {
      return;
    }

    dispatchShortcut(shortcuts, event);
  }
</script>

<!-- Capture phase, so that the shortcuts take precedence over the notebook's own (e.g. JupyterLab's command mode ones). -->
<svelte:window onkeydowncapture={onkeydown} />

<div class={[
  "w-full flex flex-row gap-2 justify-center text-sm text-slate-600",
  extraClass,
]}>
  <div class="min-w-48 flex-1 py-1 overflow-x-auto scrollbar-hidden">
    <div class="flex w-max gap-2 whitespace-nowrap">
      <span>Keyboard shortcuts:</span>
      {#each help as { keys, text }, i}
        <span>
          {#each keys as combo, j}
            {#if j > 0}/{/if}
            {#each combo as key, k}
              {#if k > 0}+{/if}<kbd>{key}</kbd>
            {/each}
          {/each}
          &ndash; {text}{i == help.length - 1 ? "." : ";"}
        </span>
      {/each}
    </div>
  </div>

  <label class="ml-auto toggle">
    <span class="mr-3">Keyboard shortcuts</span>
    <input
      type="checkbox"
      class="sr-only toggle-input"
      checked={hotkeysEnabled}
      onchange={(event) => updateHotkeysEnabled(event.currentTarget.checked)}
    />
    <div class="toggle-track"></div>
  </label>
</div>

<style lang="postcss">
  @reference "./app.css";

  kbd {
    @apply align-baseline p-1 text-xs font-semibold text-slate-600 border-gray-400 bg-gray-200 border rounded-lg;
  }

  .toggle {
    @apply inline-flex items-center not-disabled:cursor-pointer select-none;
  }

  .toggle-track {
    @apply relative h-6 min-w-11 w-11 rounded-full bg-slate-300 transition-colors duration-200;
  }

  .toggle-track::after {
    content: '';
    @apply absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200;
  }

  .toggle-input:checked + .toggle-track {
    @apply bg-emerald-500;
  }

  .toggle-input:checked + .toggle-track::after {
    transform: translateX(1.25rem);
  }
</style>
