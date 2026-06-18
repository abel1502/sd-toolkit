<script lang="ts">
  import { shortcut, type ShortcutEventDetail, type ShortcutModifierDefinition } from './shortcut';

  interface Props {
    class?: string;
  };

  let { class: extraClass = "" }: Props = $props();

  let hotkeysEnabled = $state(false);

  function handleNumber(event: ShortcutEventDetail) {
    // TODO
  }

  // TODO: remove `hotkey` from group and identify it with the index (same as how groups are communicated anyway) (remember to offset by 1, and have no hotkey for >9).
</script>

<svelte:window
  use:shortcut={{
    trigger: [
      ...Array.from({ length: 9 }, (_, i) => ({
        code: `Digit${i + 1}`,
        modifier: ['none', 'shift', 'ctrl'] as ShortcutModifierDefinition,
        callback: handleNumber,
        enabled: hotkeysEnabled,
      })),
      // TODO: Handle other shortcuts
    ]
  }}
/>

<div class={[
  "w-full flex flex-row gap-2 justify-center text-sm text-slate-600",
  extraClass,
]}>
  <!-- TODO: Make the descriptions scrollable on smaller screens -->
  <span>Keyboad shortcuts:</span>
  <span><kbd>1</kbd>&dash;<kbd>9</kbd> &ndash; toggle group;</span>
  <span><kbd>Shift</kbd>+... &ndash; enable;</span>
  <span><kbd>Ctrl</kbd>+... &ndash; disable;</span>
  <span><kbd>Space</kbd> &ndash; next image;</span>
  <span><kbd>Shift</kbd>+... &ndash; previous;</span>
  <span><kbd>Ctrl</kbd>+<kbd>Z</kbd> &ndash; undo changes to image.</span>

  <label class="ml-auto toggle">
    <span class="mr-3">Keyboard shortcuts</span>
    <input type="checkbox" class="sr-only toggle-input" bind:checked={hotkeysEnabled} />
    <div class="toggle-track"></div>
  </label>
</div>

<style lang="postcss">
  @reference "./app.css";

  kbd {
    @apply align-baseline p-1 text-xs font-semibold text-gray-600 border-gray-400 bg-gray-200 border rounded-lg;
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
