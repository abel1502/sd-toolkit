<script lang="ts">
  import type { Component, Snippet } from "svelte";
  import type { HTMLButtonAttributes } from "svelte/elements";
  import IconLoader from "@lucide/svelte/icons/loader-circle";
  import type { ActionState } from "./notifier.svelte";

  interface Props extends HTMLButtonAttributes {
    /**
     * - `default`: gray
     * - `primary`: blue, for the main action
     * - `danger`: gray, turning red on hover (e.g. for deleting)
     * - `confirm-danger`: solid red (e.g. for confirming a deletion)
     */
    variant?: "default" | "primary" | "danger" | "confirm-danger";
    /** Highlights the button (e.g. the currently selected tool). */
    active?: boolean;
    size?: "md" | "sm";
    icon?: Component<any>;
    /** The state of the button's action (see `ActionStatus`): shows a spinner while pending, then flashes. */
    status?: ActionState;
    children?: Snippet;
  };

  let {
    variant = "default",
    active = false,
    size = "md",
    icon: Icon,
    status = "idle",
    children,
    class: extraClass = "",
    type = "button",
    ...rest
  }: Props = $props();
</script>

<button
  class={[
    "btn",
    `btn--${size}`,
    active ? "btn--active" : `btn--${variant}`,
    status == "success" && "flash-success",
    status == "error" && "flash-error",
    extraClass,
  ]}
  aria-busy={status == "pending"}
  {type}
  {...rest}
>
  {#if status == "pending"}
    <IconLoader class={[size == "sm" ? "w-3.5 h-3.5 shrink-0" : "w-4 h-4 shrink-0", "animate-spin"]} />
  {:else if Icon}
    <Icon class={size == "sm" ? "w-3.5 h-3.5 shrink-0" : "w-4 h-4 shrink-0"} />
  {/if}
  {@render children?.()}
</button>

<style lang="postcss">
  @reference "./app.css";

  .btn {
    @apply inline-flex flex-row items-center justify-center ring-1 transition-colors duration-100 disabled:opacity-50;
  }

  .btn--md {
    @apply gap-1.5 px-3 py-1.5 text-sm rounded-lg;
  }

  .btn--sm {
    @apply gap-1 px-2 py-1 text-xs rounded-md;
  }

  .btn--default {
    @apply bg-gray-50 text-gray-700 ring-gray-300 not-disabled:hover:bg-gray-100;
  }

  .btn--primary {
    @apply bg-blue-50 text-blue-800 ring-blue-300 not-disabled:hover:bg-blue-100;
  }

  .btn--active {
    @apply bg-blue-100 text-blue-800 ring-blue-400 not-disabled:hover:bg-blue-50;
  }

  .btn--danger {
    @apply bg-gray-50 text-gray-700 ring-gray-300 not-disabled:hover:bg-red-50 not-disabled:hover:text-red-700;
  }

  .btn--confirm-danger {
    @apply bg-red-600 text-white ring-red-400 not-disabled:hover:bg-red-700;
  }

  .flash-success {
    animation: flash-success 900ms ease-out;
  }

  .flash-error {
    animation: flash-error 1500ms ease-out;
  }

  @keyframes flash-success {
    from {
      background-color: rgb(209 250 229);
      box-shadow: 0 0 0 3px rgb(52 211 153 / 0.5);
    }
  }

  @keyframes flash-error {
    from {
      background-color: rgb(254 226 226);
      box-shadow: 0 0 0 3px rgb(248 113 113 / 0.5);
    }
  }
</style>
