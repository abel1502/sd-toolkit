<svelte:options runes={true} />

<script lang="ts">
  interface Props {
    bindings?: {
      image_path: string;
    };
  };

  let { bindings }: Props = $props();
</script>


<div>
  <!-- <img src={bindings?.image_path} alt="" /> -->
  <!-- <p>Hello! Displaying {bindings?.image_path}</p> -->
  <div class="bg-blue-500 text-black font-bold rounded-full px-4 py-1 w-min">test</div>
</div>


