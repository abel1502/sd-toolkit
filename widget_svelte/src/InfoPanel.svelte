<script lang="ts">
  import type { InfoItem } from "./types";

  interface Props {
    items: InfoItem[];
    class?: string;
  };

  let { items, class: extraClass = "" }: Props = $props();
</script>

<div class={["text-sm border border-gray-300 rounded-lg bg-gray-50 p-2", extraClass]}>
  <table class="w-full table-fixed">
    <tbody>
      {#each items as { key, value }}
        <tr class="align-top">
          <th class="w-28 pr-2 py-0.5 text-left font-semibold text-slate-600">{key}</th>
          <td class="py-0.5 text-slate-800 break-all whitespace-pre-wrap">{value}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
