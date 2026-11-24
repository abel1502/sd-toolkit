<script lang="ts">
  import { onDestroy, untrack } from "svelte";
  import type { WidgetProps } from "./anywidget.svelte";
  import { useTrait } from "./anywidget.svelte";
  import { ImageLoader } from "./imageLoader";
  import type { TagDisplay, ViewerTraits } from "./types";
  import TagList from "./TagList.svelte";
  import Viewer from "./Viewer.svelte";

  type Traits = ViewerTraits & {
    tags: TagDisplay[];
    tags_text: string;
  };

  // These mustn't ever change, so we get rid of reactivity here.
  let _props: WidgetProps<Traits> = $props();
  let { model, experimental } = untrack(() => _props);

  const loader = new ImageLoader(experimental);
  onDestroy(() => loader.dispose());

  const tags = useTrait(model, "tags");
  const tagsText = useTrait(model, "tags_text");

  let showText = $state(false);
</script>

<Viewer {model} {loader} showInfo={true}>
  {#snippet side()}
    <div class="flex flex-row items-center justify-between">
      <span class="text-sm font-semibold text-slate-600">Tags ({tags.value.length})</span>
      <label class="text-xs text-slate-500 flex items-center gap-1 cursor-pointer select-none">
        <input type="checkbox" bind:checked={showText} />
        as text
      </label>
    </div>
    {#if showText}
      <textarea
        class="w-full min-h-24 text-sm font-mono p-2 border border-gray-300 rounded-lg bg-gray-50"
        readonly
        value={tagsText.value}
        onfocus={(event) => event.currentTarget.select()}
      ></textarea>
    {:else}
      <TagList tags={tags.value} />
    {/if}
  {/snippet}
</Viewer>
