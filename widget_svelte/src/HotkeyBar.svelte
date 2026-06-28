<script lang="ts">
  import { shortcut, type ShortcutEventDetail, type ShortcutModifierDefinition } from '@svelte-put/shortcut';

  import type { TagGroupInfo, ToggleGroupEvent } from "./types";
  import { isGroupPresent } from "./utils";

  interface Props {
    tagGroups: TagGroupInfo[];
    toggleGroup: (event: ToggleGroupEvent) => void;
    nextImage: () => void;
    prevImage: () => void;
    class?: string;
  };

  let { tagGroups, toggleGroup, nextImage, prevImage, class: extraClass = "" }: Props = $props();

  let hotkeysEnabled = $state(false);

  function handleGroupToggle(event: ShortcutEventDetail) {
    console.log("Group toggle");
    let hotkey = event.trigger.code!.at(-1)!.toLowerCase();

    let idx = tagGroups.findIndex(g => g.hotkey?.toLowerCase() === hotkey);

    if (idx >= 0) {
      let group = tagGroups[idx];

      let present: boolean;
      if (event.originalEvent.shiftKey) {
        present = true;
      } else if (event.originalEvent.ctrlKey) {
        present = false;
      } else {
        present = !isGroupPresent(group);
      }

      console.log(`Toggling group ${idx} to ${present}`);
      toggleGroup({ idx, present });
      event.originalEvent.preventDefault();
    }

    console.log("Group toggle done");
  }

  function handleNextImage(event: ShortcutEventDetail) {
    nextImage();
    event.originalEvent.preventDefault();
  }

  function handlePrevImage(event: ShortcutEventDetail) {
    prevImage();
    event.originalEvent.preventDefault();
  }

  function handleUndo(event: ShortcutEventDetail) {
    // TODO
    console.log("Not implemented: undo");
  }
</script>

<svelte:window
  use:shortcut={{
    trigger: [
      ...Array.from({ length: 10 }, (_, i) => ({
        code: `Digit${i}`,  // Digit0 ... Digit9
        modifier: ['none', 'shift', 'ctrl'] as ShortcutModifierDefinition,
        callback: handleGroupToggle,
        enabled: hotkeysEnabled,
      })),
      ...Array.from({ length: 26 }, (_, i) => ({
        code: `Key${String.fromCharCode(65 + i)}`,  // KeyA ... KeyZ
        modifier: ['none', 'shift', 'ctrl'] as ShortcutModifierDefinition,
        callback: handleGroupToggle,
        enabled: hotkeysEnabled,
      })),
      {
        code: 'Space',
        modifier: 'none',
        callback: handleNextImage,
        enabled: hotkeysEnabled,
      },
      {
        code: 'Space',
        modifier: 'shift',
        callback: handlePrevImage,
        enabled: hotkeysEnabled,
      },
      {
        code: 'Backspace',
        modifier: 'none',
        callback: handleUndo,
        enabled: hotkeysEnabled,
      },
    ]
  }}
/>

<div class={[
  "w-full flex flex-row gap-2 justify-center text-sm text-slate-600",
  extraClass,
]}>
  <div class="min-w-48 flex-1 py-1 overflow-x-auto scrollbar-hidden">
    <div class="flex w-max gap-2 whitespace-nowrap">
      <span>Keyboard shortcuts:</span>
      <span>group hotkey &ndash; toggle group;</span>
      <span><kbd>Shift</kbd>+... &ndash; enable group;</span>
      <span><kbd>Ctrl</kbd>+... &ndash; disable group;</span>
      <span><kbd>Space</kbd> &ndash; next image;</span>
      <span><kbd>Shift</kbd>+<kbd>Space</kbd> &ndash; previous image;</span>
      <span><kbd>Backspace</kbd> &ndash; reset current image.</span>
    </div>
  </div>

  <label class="ml-auto toggle">
    <span class="mr-3">Keyboard shortcuts</span>
    <input type="checkbox" class="sr-only toggle-input" bind:checked={hotkeysEnabled} />
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
