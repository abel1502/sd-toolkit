import type { TagGroupInfo } from "./types";

export function isGroupPresent(tagGroup: TagGroupInfo, tagPresence: Record<string, boolean>) {
  return tagGroup.tags.map(t => tagPresence[t.path_str]).reduce((a, b) => a && b, true);
}
