import type { TagGroupInfo } from "./types";

export function isGroupPresent(tagGroup: TagGroupInfo) {
  return tagGroup.tags.map(t => t.present).reduce((a, b) => a && b, true);
}
