<script lang="ts" module>
  /** `[left, top, right, bottom]`, in image pixels. */
  export type Box = [number, number, number, number];

  /** Exact integer proportions, or `null` for any proportions. */
  export type Ratio = { width: number, height: number } | null;

  export interface CanvasCrop {
    path: string;
    box: Box;
    locked: boolean;
  };

  type Point = [number, number];

  /** Which sides of the box a handle moves, e.g. `"nw"` or `"e"`. */
  type Handle = "nw" | "ne" | "sw" | "se" | "n" | "s" | "e" | "w";

  const CORNERS: Handle[] = ["nw", "ne", "sw", "se"];
  const EDGES: Handle[] = ["n", "s", "e", "w"];

  /** Boxes smaller than this (in image pixels) aren't created. */
  const MIN_SIZE = 8;

  export function boxSize(box: Box): [number, number] {
    return [box[2] - box[0], box[3] - box[1]];
  }

  /**
   * The largest box with the given proportions fitting into the image, scaled by `fraction`,
   * and centered at `center` as closely as the image bounds allow.
   */
  export function centeredBox(center: Point, ratio: Ratio, imageSize: [number, number], fraction: number = 1): Box {
    const [width, height] = imageSize;

    let w: number;
    let h: number;
    if (ratio) {
      const k = Math.max(1, Math.floor(Math.min(width / ratio.width, height / ratio.height) * fraction));
      [w, h] = [ratio.width * k, ratio.height * k];
    } else {
      [w, h] = [Math.round(width * fraction), Math.round(height * fraction)];
    }

    return placeBox(center, w, h, imageSize);
  }

  /** Resizes the box to the given proportions, keeping its center and (roughly) its area. */
  export function reshapeBox(box: Box, ratio: Ratio, imageSize: [number, number]): Box {
    if (!ratio) return box;

    const [w, h] = boxSize(box);
    const kMax = Math.floor(Math.min(imageSize[0] / ratio.width, imageSize[1] / ratio.height));
    const k = Math.max(1, Math.min(kMax, Math.round(Math.sqrt((w * h) / (ratio.width * ratio.height)))));

    return placeBox(boxCenter(box), ratio.width * k, ratio.height * k, imageSize);
  }

  /** Scales the box around its center, keeping exact proportions if specified. */
  export function scaleBox(box: Box, factor: number, ratio: Ratio, imageSize: [number, number]): Box {
    const [w, h] = boxSize(box);

    if (ratio && w * ratio.height == h * ratio.width) {
      const k = w / ratio.width;
      const kMax = Math.floor(Math.min(imageSize[0] / ratio.width, imageSize[1] / ratio.height));
      const newK = Math.max(1, Math.min(kMax, factor > 1 ? Math.max(k + 1, Math.round(k * factor)) : Math.min(k - 1, Math.round(k * factor))));
      return placeBox(boxCenter(box), ratio.width * newK, ratio.height * newK, imageSize);
    }

    const scale = Math.min(factor, imageSize[0] / w, imageSize[1] / h);
    return placeBox(boxCenter(box), Math.max(MIN_SIZE, Math.round(w * scale)), Math.max(MIN_SIZE, Math.round(h * scale)), imageSize);
  }

  function boxCenter(box: Box): Point {
    return [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2];
  }

  function placeBox(center: Point, w: number, h: number, [width, height]: [number, number]): Box {
    w = Math.min(w, width);
    h = Math.min(h, height);
    const left = Math.round(Math.max(0, Math.min(width - w, center[0] - w / 2)));
    const top = Math.round(Math.max(0, Math.min(height - h, center[1] - h / 2)));
    return [left, top, left + w, top + h];
  }

  /**
   * A box spanned between a fixed `anchor` corner and `point`, limited to the image.
   * `axes` says which dimensions follow the point (the others are taken from `base`).
   */
  function spanBox(anchor: Point, point: Point, ratio: Ratio, [width, height]: [number, number], base: Box | null = null, axes: [boolean, boolean] = [true, true]): Box {
    const dx = point[0] - anchor[0];
    const dy = point[1] - anchor[1];
    const sx = dx < 0 ? -1 : 1;
    const sy = dy < 0 ? -1 : 1;
    const maxW = sx > 0 ? width - anchor[0] : anchor[0];
    const maxH = sy > 0 ? height - anchor[1] : anchor[1];

    let w: number;
    let h: number;
    if (ratio) {
      const kMax = Math.floor(Math.min(maxW / ratio.width, maxH / ratio.height));
      const k = Math.max(0, Math.min(kMax, Math.round(Math.max(Math.abs(dx) / ratio.width, Math.abs(dy) / ratio.height))));
      [w, h] = [ratio.width * k, ratio.height * k];
    } else {
      w = Math.round(Math.min(Math.abs(dx), maxW));
      h = Math.round(Math.min(Math.abs(dy), maxH));
    }

    let [left, top, right, bottom]: Box = [
      sx > 0 ? anchor[0] : anchor[0] - w,
      sy > 0 ? anchor[1] : anchor[1] - h,
      sx > 0 ? anchor[0] + w : anchor[0],
      sy > 0 ? anchor[1] + h : anchor[1],
    ];

    if (base && !axes[0]) [left, right] = [base[0], base[2]];
    if (base && !axes[1]) [top, bottom] = [base[1], base[3]];

    return [left, top, right, bottom];
  }

  function isValid(box: Box): boolean {
    const [w, h] = boxSize(box);
    return w >= MIN_SIZE && h >= MIN_SIZE;
  }

  function sameBox(a: Box, b: Box): boolean {
    return a.every((value, i) => value == b[i]);
  }
</script>

<script lang="ts">
  interface Props {
    imageUrl: string;
    imageSize: [number, number];
    crops: CanvasCrop[];
    /** The path of the selected crop. */
    selected: string | null;
    /** The proportions for new (and resized) crops. */
    ratio: Ratio;
    /** The size of crops created by clicking, relative to the largest possible one. */
    sizeFraction: number;
    /** Creates (`path == null`) or replaces a crop. Should resolve once the crops are updated. */
    oncommit: (path: string | null, box: Box) => Promise<void>;
  };

  let { imageUrl, imageSize, crops, selected = $bindable(), ratio, sizeFraction, oncommit }: Props = $props();

  let containerWidth = $state(0);
  let containerHeight = $state(0);
  let scale = $derived(
    imageSize[0] && imageSize[1]
      ? Math.min(containerWidth / imageSize[0], containerHeight / imageSize[1])
      : 0
  );

  let svg: SVGSVGElement | undefined = $state();

  type Drag =
    | { kind: "pending", start: Point, screenStart: Point }
    | { kind: "draw", anchor: Point }
    | { kind: "move", path: string, original: Box, start: Point }
    | { kind: "resize", path: string, original: Box, handle: Handle };

  let drag: Drag | null = null;
  /** The box being dragged, shown instead of the saved one. */
  let draft = $state<{ path: string | null, box: Box } | null>(null);

  let selectedCrop = $derived(crops.find(crop => crop.path == selected) ?? null);

  let shownCrops: CanvasCrop[] = $derived.by(() => {
    const result = crops.map(crop => draft && draft.path == crop.path ? { ...crop, box: draft.box } : crop);
    if (draft && draft.path === null) {
      result.push({ path: "", box: draft.box, locked: false });
    }
    return result;
  });

  let focusBox: Box | null = $derived(draft?.box ?? selectedCrop?.box ?? null);

  function toImage(event: PointerEvent | WheelEvent): Point {
    const rect = svg!.getBoundingClientRect();
    return [
      Math.max(0, Math.min(imageSize[0], (event.clientX - rect.left) / rect.width * imageSize[0])),
      Math.max(0, Math.min(imageSize[1], (event.clientY - rect.top) / rect.height * imageSize[1])),
    ];
  }

  /** The handle grab radius, in image pixels. */
  let grab = $derived(scale ? 8 / scale : 8);

  function handlePoint(box: Box, handle: Handle): Point {
    const x = handle.includes("w") ? box[0] : handle.includes("e") ? box[2] : (box[0] + box[2]) / 2;
    const y = handle.includes("n") ? box[1] : handle.includes("s") ? box[3] : (box[1] + box[3]) / 2;
    return [x, y];
  }

  let handles: Handle[] = $derived(ratio ? CORNERS : [...CORNERS, ...EDGES]);

  function hitHandle(box: Box, point: Point): Handle | null {
    for (const handle of handles) {
      const [x, y] = handlePoint(box, handle);
      if (Math.abs(point[0] - x) <= grab && Math.abs(point[1] - y) <= grab) {
        return handle;
      }
    }
    return null;
  }

  function contains(box: Box, point: Point): boolean {
    return point[0] >= box[0] && point[0] <= box[2] && point[1] >= box[1] && point[1] <= box[3];
  }

  function onpointerdown(event: PointerEvent) {
    if (event.button != 0) return;

    const point = toImage(event);
    svg!.setPointerCapture(event.pointerId);

    if (selectedCrop && !selectedCrop.locked) {
      const handle = hitHandle(selectedCrop.box, point);
      if (handle) {
        drag = { kind: "resize", path: selectedCrop.path, original: selectedCrop.box, handle };
        return;
      }
    }

    // Prefer the selected crop, then the smallest one under the pointer
    const hit = [...crops]
      .filter(crop => contains(crop.box, point))
      .sort((a, b) => (a.path == selected ? -1 : 0) - (b.path == selected ? -1 : 0)
        || boxSize(a.box)[0] * boxSize(a.box)[1] - boxSize(b.box)[0] * boxSize(b.box)[1])[0];

    if (hit) {
      selected = hit.path;
      if (!hit.locked) {
        drag = { kind: "move", path: hit.path, original: hit.box, start: point };
      }
      return;
    }

    drag = { kind: "pending", start: point, screenStart: [event.clientX, event.clientY] };
  }

  function onpointermove(event: PointerEvent) {
    if (!drag) return;

    const point = toImage(event);

    switch (drag.kind) {
      case "pending": {
        const moved = Math.hypot(event.clientX - drag.screenStart[0], event.clientY - drag.screenStart[1]);
        if (moved < 5) return;
        drag = { kind: "draw", anchor: [Math.round(drag.start[0]), Math.round(drag.start[1])] };
        selected = null;
        draft = { path: null, box: spanBox(drag.anchor, point, ratio, imageSize) };
        break;
      }
      case "draw":
        draft = { path: null, box: spanBox(drag.anchor, point, ratio, imageSize) };
        break;
      case "move": {
        const [w, h] = boxSize(drag.original);
        const left = Math.round(Math.max(0, Math.min(imageSize[0] - w, drag.original[0] + point[0] - drag.start[0])));
        const top = Math.round(Math.max(0, Math.min(imageSize[1] - h, drag.original[1] + point[1] - drag.start[1])));
        draft = { path: drag.path, box: [left, top, left + w, top + h] };
        break;
      }
      case "resize": {
        const handle = drag.handle;
        // The opposite corner (or edge) stays in place
        const opposite = handle
          .replace("n", "S").replace("s", "N").replace("e", "W").replace("w", "E")
          .toLowerCase() as Handle;
        const anchor = handlePoint(drag.original, opposite);
        const axes: [boolean, boolean] = [/[ew]/.test(handle), /[ns]/.test(handle)];
        draft = { path: drag.path, box: spanBox(anchor, point, ratio, imageSize, drag.original, axes) };
        break;
      }
    }
  }

  function onpointerup(event: PointerEvent) {
    if (!drag) return;

    const finished = drag;
    drag = null;

    if (finished.kind == "pending") {
      draft = null;
      if (ratio === null) {
        // Without fixed proportions, there's no sensible box to create from a click
        selected = null;
        return;
      }
      commit(null, centeredBox(finished.start, ratio, imageSize, sizeFraction));
      return;
    }

    if (event.type == "pointercancel" || !draft || !isValid(draft.box)) {
      draft = null;
      return;
    }

    if (finished.kind != "draw" && sameBox(draft.box, finished.original)) {
      draft = null;
      return;
    }

    commit(draft.path, draft.box);
  }

  function commit(path: string | null, box: Box) {
    // Keep showing the box until the new crops arrive
    draft = { path, box };
    oncommit(path, box).finally(() => {
      if (!drag) draft = null;
    });
  }

  function onwheel(event: WheelEvent) {
    if (!selectedCrop || selectedCrop.locked || drag) return;
    if (!contains(selectedCrop.box, toImage(event))) return;

    event.preventDefault();

    // The crop isn't updated until the burst of wheel events ends, so continue from the draft
    const current = draft?.path == selectedCrop.path ? draft.box : selectedCrop.box;
    const box = scaleBox(current, event.deltaY < 0 ? 1.05 : 1 / 1.05, ratio, imageSize);
    if (!sameBox(box, current)) {
      commitDebounced(selectedCrop.path, box);
    }
  }

  let wheelTimeout: ReturnType<typeof setTimeout> | undefined;
  function commitDebounced(path: string, box: Box) {
    draft = { path, box };
    clearTimeout(wheelTimeout);
    wheelTimeout = setTimeout(() => commit(path, box), 300);
  }

  let overlayPath = $derived(
    focusBox
      ? `M0 0H${imageSize[0]}V${imageSize[1]}H0Z M${focusBox[0]} ${focusBox[1]}V${focusBox[3]}H${focusBox[2]}V${focusBox[1]}Z`
      : ""
  );
</script>

<div class="w-full h-full relative" bind:clientWidth={containerWidth} bind:clientHeight={containerHeight}>
  <div
    class="absolute"
    style:left="{(containerWidth - imageSize[0] * scale) / 2}px"
    style:top="{(containerHeight - imageSize[1] * scale) / 2}px"
    style:width="{imageSize[0] * scale}px"
    style:height="{imageSize[1] * scale}px"
  >
    <img src={imageUrl} alt="Cropped" class="absolute inset-0 w-full h-full select-none" draggable="false" />
    <svg
      bind:this={svg}
      class="absolute inset-0 w-full h-full touch-none cursor-crosshair"
      viewBox="0 0 {imageSize[0]} {imageSize[1]}"
      preserveAspectRatio="none"
      role="presentation"
      {onpointerdown}
      {onpointermove}
      {onpointerup}
      onpointercancel={onpointerup}
      {onwheel}
    >
      {#if overlayPath}
        <path d={overlayPath} fill="black" fill-opacity="0.45" fill-rule="evenodd" pointer-events="none" />
      {/if}

      {#each shownCrops as crop (crop.path)}
        {@const isSelected = crop.path == selected || (crop.path == "" && draft?.path === null)}
        <rect
          x={crop.box[0]}
          y={crop.box[1]}
          width={boxSize(crop.box)[0]}
          height={boxSize(crop.box)[1]}
          fill="transparent"
          stroke={isSelected ? "#22d3ee" : "white"}
          stroke-width={isSelected ? 2.5 : 1.5}
          stroke-dasharray={crop.locked ? "6 4" : undefined}
          vector-effect="non-scaling-stroke"
          class={crop.locked ? "cursor-not-allowed" : "cursor-move"}
          style:filter="drop-shadow(0 0 1px rgba(0, 0, 0, 0.8))"
        />
      {/each}

      {#if selectedCrop && !selectedCrop.locked && !draft}
        {#each handles as handle}
          {@const [x, y] = handlePoint(selectedCrop.box, handle)}
          <rect
            x={x - grab / 2}
            y={y - grab / 2}
            width={grab}
            height={grab}
            fill="white"
            stroke="#0891b2"
            stroke-width="1"
            vector-effect="non-scaling-stroke"
            pointer-events="none"
          />
        {/each}
      {/if}
    </svg>
  </div>
</div>
