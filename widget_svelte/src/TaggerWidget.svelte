<svelte:options runes={true} />

<script lang="ts">
  interface Props {
    bindings?: {
      image_path: string;
    };
  };

  let { bindings }: Props = $props();
</script>

<img src={bindings?.image_path} alt="" />

<!-- <p>Hello! Displaying {bindings?.image_path}</p> -->

