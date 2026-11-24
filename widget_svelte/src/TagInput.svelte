<script lang="ts">
  import IconPlus from "@lucide/svelte/icons/plus";

  interface Props {
    vocabulary: string[];
    /** Tags to exclude from suggestions (e.g. the ones already present). */
    exclude?: Set<string>;
    onsubmit: (text: string) => void;
    input?: HTMLInputElement;
  };

  let { vocabulary, exclude = new Set(), onsubmit, input = $bindable() }: Props = $props();

  const MAX_SUGGESTIONS = 8;

  let text = $state("");
  let highlighted = $state(-1);
  let focused = $state(false);

  // Suggestions complete the last comma-separated fragment
  let fragmentStart = $derived(text.lastIndexOf(",") + 1);
  let fragment = $derived(normalize(text.slice(fragmentStart)));

  function normalize(value: string): string {
    return value.trim().toLowerCase().replaceAll("_", " ");
  }

  let normalizedVocabulary = $derived(vocabulary.map(tag => [tag, normalize(tag)] as const));

  let suggestions: string[] = $derived.by(() => {
    if (!fragment) return [];

    const prefixMatches: string[] = [];
    const otherMatches: string[] = [];

    for (const [tag, normalized] of normalizedVocabulary) {
      if (exclude.has(tag) || normalized == fragment) continue;

      if (normalized.startsWith(fragment) || normalized.includes("::" + fragment)) {
        prefixMatches.push(tag);
        if (prefixMatches.length >= MAX_SUGGESTIONS) break;
      } else if (otherMatches.length < MAX_SUGGESTIONS && normalized.includes(fragment)) {
        otherMatches.push(tag);
      }
    }

    return [...prefixMatches, ...otherMatches].slice(0, MAX_SUGGESTIONS);
  });

  $effect(() => {
    // Reset the highlight whenever the suggestions change
    suggestions;
    highlighted = -1;
  });

  function accept(suggestion: string) {
    const prefix = text.slice(0, fragmentStart);
    text = (prefix ? prefix.trimEnd() + " " : "") + suggestion + ", ";
    input?.focus();
  }

  function submit() {
    const value = text.trim().replace(/,$/, "").trim();
    if (!value) return;
    onsubmit(value);
    text = "";
  }

  function onkeydown(event: KeyboardEvent) {
    const showing = focused && suggestions.length > 0;

    switch (event.key) {
      case "ArrowDown":
        if (!showing) return;
        highlighted = (highlighted + 1) % suggestions.length;
        break;
      case "ArrowUp":
        if (!showing) return;
        highlighted = (highlighted - 1 + suggestions.length) % suggestions.length;
        break;
      case "Tab":
        if (!showing) return;
        accept(suggestions[Math.max(0, highlighted)]);
        break;
      case "Enter":
        if (showing && highlighted >= 0) {
          accept(suggestions[highlighted]);
        } else {
          submit();
        }
        break;
      case "Escape":
        if (showing) {
          highlighted = -1;
          focused = false;
        } else {
          input?.blur();
        }
        break;
      default:
        return;
    }

    event.preventDefault();
    event.stopPropagation();
  }
</script>

<div class="relative">
  <div class="flex flex-row gap-2">
    <input
      bind:this={input}
      bind:value={text}
      class="flex-1 min-w-0 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300"
      placeholder="Add tags: tag, other tag, parent::child"
      spellcheck="false"
      autocomplete="off"
      {onkeydown}
      onfocus={() => { focused = true; }}
      onblur={() => { focused = false; }}
      oninput={() => { focused = true; }}
    />
    <button
      class="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg ring-1 ring-blue-300 bg-blue-50 text-blue-800 hover:bg-blue-100 disabled:opacity-50"
      disabled={!text.trim()}
      onclick={submit}
    >
      <IconPlus class="w-4 h-4" />
      Add
    </button>
  </div>

  {#if focused && suggestions.length > 0}
    <ul class="absolute z-40 left-0 right-0 mt-1 py-1 bg-white border border-gray-300 rounded-lg shadow-md text-sm">
      {#each suggestions as suggestion, i (suggestion)}
        <li>
          <button
            class={["w-full text-left px-3 py-1", i == highlighted ? "bg-blue-100" : "hover:bg-gray-100"]}
            onmousedown={(event) => { event.preventDefault(); accept(suggestion); }}
          >
            {suggestion}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
