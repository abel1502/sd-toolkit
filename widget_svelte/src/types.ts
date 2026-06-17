export interface TagGroupInfo {
  tags: TagInfo[];
  subgroups: TagGroupInfo[];
  hotkey: string | null;
}

export interface TagInfo {
  tag: string;
  path: string[];
  present: boolean;
}
