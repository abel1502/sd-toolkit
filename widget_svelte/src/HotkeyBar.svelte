<script lang="ts">
  import { onDestroy, onMount } from "svelte";

  import { enabledHotkeys, dispatchShortcut, type Shortcut, type ShortcutHelp } from "./hotkeys";
  import Toggle from "./Toggle.svelte";

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

  // A newly rendered widget takes the shortcuts over, since it's most likely the one the user wants to use
  onMount(() => enabledHotkeys.set(hotkeyScope));
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

  <Toggle class="ml-auto" checked={hotkeysEnabled} onchange={updateHotkeysEnabled}>
    Keyboard shortcuts
  </Toggle>
</div>

<style lang="postcss">
  @reference "./app.css";

  kbd {
    @apply align-baseline p-1 text-xs font-semibold text-slate-600 border-gray-400 bg-gray-200 border rounded-lg;
  }
</style>
