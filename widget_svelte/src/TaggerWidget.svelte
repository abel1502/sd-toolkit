<script lang="ts">
  import IconSave from "@lucide/svelte/icons/save";
  import IconSaveOff from "@lucide/svelte/icons/save-off";
  import IconRotateCCW from "@lucide/svelte/icons/rotate-ccw";
  import { onDestroy, untrack } from "svelte";
  import type { WidgetProps } from "./anywidget.svelte";
  import { useTrait, sendMessage } from "./anywidget.svelte";
  import { ImageLoader } from "./imageLoader";
  import { hotkeyCode, type Shortcut, type Modifier } from "./hotkeys";
  import type { TagGroupInfo, ToggleTagEvent, ToggleGroupEvent, ViewerTraits } from "./types";
  import { isGroupPresent } from "./utils";
  import TagsPanel from "./TagsPanel.svelte";
  import Viewer from "./Viewer.svelte";

  type Traits = ViewerTraits & {
    tag_groups: TagGroupInfo[];
    tag_presence: Record<string, boolean>;
  };

  // These mustn't ever change, so we get rid of reactivity here.
  let _props: WidgetProps<Traits> = $props();
  let { model, experimental } = untrack(() => _props);

  const loader = new ImageLoader(experimental);
  onDestroy(() => loader.dispose());

  const tagGroups = useTrait(model, "tag_groups");
  const tagPresence = useTrait(model, "tag_presence");

  function toggleTag(event: ToggleTagEvent) {
    // TODO: Add a spinner while waiting for updates from python somehow?
    sendMessage(model, "toggle_tag", { ...event });
  }

  function toggleGroup(event: ToggleGroupEvent) {
    // TODO: Add a spinner while waiting for updates from python somehow?
    sendMessage(model, "toggle_group", { ...event });
  }

  function revertImage() {
    sendMessage(model, "revert_image");
  }

  function handleGroupHotkey(idx: number, modifier: Modifier | null) {
    const group = tagGroups.value[idx];

    let present: boolean;
    if (modifier == "shift") {
      present = true;
    } else if (modifier == "ctrl") {
      present = false;
    } else {
      present = !isGroupPresent(group, tagPresence.value);
    }

    toggleGroup({ idx, present });
  }

  let shortcuts: Shortcut[] = $derived([
    ...tagGroups.value.flatMap((group, idx) => group.hotkey ? (
      ([null, "shift", "ctrl"] as (Modifier | null)[]).map(modifier => ({
        code: hotkeyCode(group.hotkey!),
        modifiers: modifier ? [modifier] : [],
        callback: () => handleGroupHotkey(idx, modifier),
      }))
    ) : []),
    { code: "Backspace", callback: revertImage },
  ]);

  // TODO: Wire up
  let autoSaveUnchanged: boolean = $state(true);
</script>

<Viewer
  {model}
  {experimental}
  {loader}
  {shortcuts}
  help={[
    { keys: [["group hotkey"]], text: "toggle group" },
    { keys: [["Shift", "..."]], text: "enable group" },
    { keys: [["Ctrl", "..."]], text: "disable group" },
    { keys: [["Backspace"]], text: "reset current image" },
  ]}
  imageButtons={[
    {
      icon: autoSaveUnchanged ? IconSave : IconSaveOff,
      title: (autoSaveUnchanged ? "Disable" : "Enable") + " saving unchanged images",
      onclick: () => { autoSaveUnchanged = !autoSaveUnchanged },
    },
    {
      icon: IconRotateCCW,
      title: "Reset image tags",
      onclick: revertImage,
    },
  ]}
>
  {#snippet side()}
    <TagsPanel tagGroups={tagGroups.value} tagPresence={tagPresence.value} {toggleGroup} {toggleTag} />
  {/snippet}
</Viewer>
