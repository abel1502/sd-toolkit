<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    checked?: boolean;
    /** Called when the user flips the toggle (in addition to updating `checked`). */
    onchange?: (checked: boolean) => void;
    size?: "md" | "sm";
    disabled?: boolean;
    title?: string;
    class?: string;
    /** The label, shown to the left of the toggle. */
    children?: Snippet;
  };

  let {
    checked = $bindable(false),
    onchange,
    size = "md",
    disabled = false,
    title,
    class: extraClass = "",
    children,
  }: Props = $props();
</script>

<label class={["toggle", `toggle--${size}`, extraClass]} {title}>
  {#if children}
    <span>{@render children()}</span>
  {/if}
  <input
    type="checkbox"
    class="sr-only toggle-input"
    bind:checked
    {disabled}
    onchange={(event) => onchange?.(event.currentTarget.checked)}
  />
  <div class="toggle-track"></div>
</label>

<style lang="postcss">
  @reference "./app.css";

  .toggle {
    @apply inline-flex items-center gap-2 select-none;
  }

  .toggle:has(.toggle-input:not(:disabled)) {
    @apply cursor-pointer;
  }

  .toggle:has(.toggle-input:disabled) {
    @apply opacity-50;
  }

  .toggle-track {
    @apply relative shrink-0 rounded-full bg-slate-300 transition-colors duration-200;
  }

  .toggle-track::after {
    content: '';
    @apply absolute left-0.5 top-0.5 rounded-full bg-white shadow-sm transition-transform duration-200;
  }

  .toggle--md .toggle-track {
    @apply h-6 w-11;
  }

  .toggle--md .toggle-track::after {
    @apply h-5 w-5;
  }

  .toggle--sm .toggle-track {
    @apply h-4 w-7;
  }

  .toggle--sm .toggle-track::after {
    @apply h-3 w-3;
  }

  .toggle-input:focus-visible + .toggle-track {
    @apply ring-2 ring-blue-300;
  }

  .toggle-input:checked + .toggle-track {
    @apply bg-emerald-500;
  }

  .toggle--md .toggle-input:checked + .toggle-track::after {
    transform: translateX(1.25rem);
  }

  .toggle--sm .toggle-input:checked + .toggle-track::after {
    transform: translateX(0.75rem);
  }
</style>
