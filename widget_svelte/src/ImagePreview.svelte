<script lang="ts">
  import IconBadgeCheck from "@lucide/svelte/icons/badge-check";

  interface Props {
    image: string;
    imageSaved: boolean;
    buttons?: {
      icon: any;  // Couldn't figure out a way to type this
      title: string;
      onclick: () => void;
    }[];
    class?: string;
  };

  let { image, imageSaved, buttons = [], class: extraClass = "" }: Props = $props();
</script>

<div class={[
  "relative grid place-items-center aspect-square bg-gray-100 rounded-lg border border-gray-300 overflow-hidden",
  extraClass,
]}>
  {#if image}
    <img src={image} alt="Preview" class="w-full h-full object-contain aspect-square"/>

    {#if imageSaved}
    <div class="absolute top-0 right-0 m-1" title="Image reviewed">
      <IconBadgeCheck class="align-middle text-green-700 w-8 h-8" />
    </div>
    {/if}

    {#if buttons}
      <div class="absolute bottom-0 right-0 px-2 py-1 bg-black/20 h-10 flex gap-2 items-center">
        {#each buttons as { icon: Icon, title, onclick }}
          <button class="text-white" {title} {onclick}>
            <Icon class="w-6 h-6" />
          </button>
        {/each}
      </div>
    {/if}
  {:else}
    <span class="text-gray-400 text-sm text-center">No Image</span>
  {/if}
</div>
