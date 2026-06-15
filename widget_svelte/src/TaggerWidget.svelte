<svelte:options runes={true} />

<script lang="ts">
  import type { AnyModel } from "@anywidget/types";

  interface Bindings {
    image: string;
    tags: Record<string, boolean>;  // TODO: Actually nested
  }

  interface Props {
    model: AnyModel<Bindings>;
    bindings?: Bindings;
  };

  let { model, bindings }: Props = $props();
  let { image, tags } = $derived(bindings ?? { image: '', tags: {} });

  function toggleTag(tagName: string) {
    if (bindings) {
      bindings.tags = { ...tags, [tagName]: !tags[tagName] };
    }
  }
</script>


<!-- <img src={bindings?.image_path} alt="" /> -->
<!-- <p>Hello! Displaying {bindings?.image_path}</p> -->

<!-- <div>
  <div class="bg-blue-500 text-black font-bold rounded-full px-4 py-1 w-min">test</div>
</div> -->

<!-- TODO: Clean up styles -->

<div class="flex flex-col w-full max-w-4xl p-4 border rounded-lg bg-white shadow-sm">

  <div class="flex flex-row md:flex-row gap-6 grow">
    
    <div class="w-full md:w-1/3 bg-gray-100 rounded-lg flex items-center justify-center border overflow-hidden">
      {#if image}
        <img 
          src={image} 
          alt="Preview" 
          class="w-full h-64 object-cover"
        />
      {:else}
        <span class="text-gray-400 text-sm">No Image</span>
      {/if}
    </div>
    
    <div class="flex-1 flex flex-row flex-wrap gap-2 h-min">
      {#each Object.keys(tags) as tagName}
        <button
          class={`
            px-4 py-2 rounded-full text-sm font-medium transition-colors duration-200
            ${tags[tagName] 
              ? 'bg-blue-100 text-blue-800 ring-1 ring-blue-300' 
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}
          `}
          onclick={() => toggleTag(tagName)}
        >
          {tagName}
        </button>
      {/each}
    </div>

  </div>

  <div class="mt-6 flex flex-row items-center gap-4">
    <button 
      class="px-4 py-2 border rounded hover:bg-gray-50 text-gray-700"
      disabled
    >
      &larr; Previous
    </button>

    <div class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
      <div class="w-1/3 h-full bg-blue-500"></div>
    </div>

    <button 
      class="px-4 py-2 border rounded hover:bg-gray-50 text-gray-700"
    >
      Next &rarr;
    </button>
  </div>

</div>


