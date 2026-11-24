<script lang="ts" module>
  export type BrushMode = "brush" | "eraser";

  type Point = [number, number];

  type Op =
    | { kind: "stroke", mode: BrushMode, radius: number, points: Point[] }
    | { kind: "clear" }
    | { kind: "invert" };

  function loadImage(url: string): Promise<HTMLImageElement> {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error(`Failed to load ${url}`));
      image.src = url;
    });
  }
</script>

<script lang="ts">
  interface Props {
    imageUrl: string;
    /** The previously saved mask to start from, if any. */
    maskUrl: string | null;
    mode: BrushMode;
    /** The brush size, in screen pixels. */
    brushSize: number;
    dirty?: boolean;
  };

  let { imageUrl, maskUrl, mode, brushSize, dirty = $bindable(false) }: Props = $props();

  const OVERLAY_COLOR = "#ff0000";

  let canvas: HTMLCanvasElement | undefined = $state();
  let ctx = $derived(canvas?.getContext("2d", { willReadFrequently: true }) ?? null);

  let natural = $state({ width: 0, height: 0 });
  let containerWidth = $state(0);
  let containerHeight = $state(0);
  let scale = $derived(
    natural.width && natural.height
      ? Math.min(containerWidth / natural.width, containerHeight / natural.height)
      : 0
  );

  let ready = $state(false);
  let error: string | null = $state(null);

  // The saved mask, converted to the overlay representation (red, with alpha = mask value)
  let baseMask: HTMLCanvasElement | null = null;
  let ops: Op[] = [];
  let currentStroke: (Op & { kind: "stroke" }) | null = null;

  function updateDirty() {
    dirty = ops.length > 0;
  }

  $effect(() => {
    const image = imageUrl;
    const mask = maskUrl;
    let cancelled = false;

    ready = false;
    error = null;

    Promise.all([loadImage(image), mask ? loadImage(mask) : null]).then(
      ([loadedImage, loadedMask]) => {
        if (cancelled || !canvas) return;

        natural = { width: loadedImage.naturalWidth, height: loadedImage.naturalHeight };
        canvas.width = natural.width;
        canvas.height = natural.height;

        baseMask = loadedMask ? maskToOverlay(loadedMask, natural.width, natural.height) : null;
        ops = [];
        currentStroke = null;
        updateDirty();
        redraw();
        ready = true;
      },
      (e) => {
        if (cancelled) return;
        error = String(e);
      },
    );

    return () => { cancelled = true; };
  });

  function maskToOverlay(mask: HTMLImageElement, width: number, height: number): HTMLCanvasElement {
    const result = document.createElement("canvas");
    result.width = width;
    result.height = height;

    const resultCtx = result.getContext("2d", { willReadFrequently: true })!;
    resultCtx.drawImage(mask, 0, 0, width, height);

    const data = resultCtx.getImageData(0, 0, width, height);
    const pixels = data.data;
    for (let i = 0; i < pixels.length; i += 4) {
      // The mask is grayscale, so any channel will do
      pixels[i + 3] = pixels[i];
      pixels[i] = 255;
      pixels[i + 1] = 0;
      pixels[i + 2] = 0;
    }
    resultCtx.putImageData(data, 0, 0);

    return result;
  }

  function redraw() {
    if (!ctx) return;

    ctx.clearRect(0, 0, natural.width, natural.height);
    if (baseMask) {
      ctx.drawImage(baseMask, 0, 0);
    }
    for (const op of ops) {
      applyOp(op);
    }
  }

  function applyOp(op: Op) {
    if (!ctx) return;

    switch (op.kind) {
      case "clear":
        ctx.clearRect(0, 0, natural.width, natural.height);
        break;
      case "invert": {
        const data = ctx.getImageData(0, 0, natural.width, natural.height);
        const pixels = data.data;
        for (let i = 0; i < pixels.length; i += 4) {
          pixels[i] = 255;
          pixels[i + 1] = 0;
          pixels[i + 2] = 0;
          pixels[i + 3] = 255 - pixels[i + 3];
        }
        ctx.putImageData(data, 0, 0);
        break;
      }
      case "stroke":
        drawStroke(op, 0);
        break;
    }
  }

  /** Draws the stroke's segments starting from point `from`. */
  function drawStroke(op: Op & { kind: "stroke" }, from: number) {
    if (!ctx) return;

    ctx.save();
    ctx.globalCompositeOperation = op.mode == "eraser" ? "destination-out" : "source-over";
    ctx.strokeStyle = OVERLAY_COLOR;
    ctx.fillStyle = OVERLAY_COLOR;
    ctx.lineWidth = op.radius * 2;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    if (op.points.length == 1) {
      const [x, y] = op.points[0];
      ctx.beginPath();
      ctx.arc(x, y, op.radius, 0, 2 * Math.PI);
      ctx.fill();
    } else {
      ctx.beginPath();
      ctx.moveTo(...op.points[Math.max(0, from - 1)]);
      for (const point of op.points.slice(Math.max(1, from))) {
        ctx.lineTo(...point);
      }
      ctx.stroke();
    }

    ctx.restore();
  }

  function toImageCoords(event: PointerEvent): Point {
    const rect = canvas!.getBoundingClientRect();
    return [
      (event.clientX - rect.left) / rect.width * natural.width,
      (event.clientY - rect.top) / rect.height * natural.height,
    ];
  }

  function onpointerdown(event: PointerEvent) {
    if (!ready || event.button != 0 || scale == 0) return;

    canvas!.setPointerCapture(event.pointerId);

    currentStroke = {
      kind: "stroke",
      mode,
      radius: brushSize / 2 / scale,
      points: [toImageCoords(event)],
    };
    ops.push(currentStroke);
    updateDirty();
    drawStroke(currentStroke, 0);
  }

  function onpointermove(event: PointerEvent) {
    updateCursor(event);

    if (!currentStroke) return;

    currentStroke.points.push(toImageCoords(event));
    drawStroke(currentStroke, currentStroke.points.length - 1);
  }

  function onpointerup() {
    currentStroke = null;
  }

  let cursor: { x: number, y: number } | null = $state(null);

  function updateCursor(event: PointerEvent) {
    const rect = canvas!.getBoundingClientRect();
    cursor = { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  export function undo() {
    if (currentStroke) return;
    ops.pop();
    updateDirty();
    redraw();
  }

  function pushOp(op: Op) {
    if (!ready) return;
    ops.push(op);
    updateDirty();
    applyOp(op);
  }

  export function clear() {
    pushOp({ kind: "clear" });
  }

  export function invert() {
    pushOp({ kind: "invert" });
  }

  /**
   * @returns The mask as a grayscale PNG (white = masked), or `null` if the mask is empty.
   */
  export async function exportMask(): Promise<Blob | null> {
    if (!ctx || !ready) return null;

    const { width, height } = natural;
    const data = ctx.getImageData(0, 0, width, height);
    const result = new ImageData(width, height);

    let empty = true;
    for (let i = 0; i < data.data.length; i += 4) {
      const value = data.data[i + 3];
      result.data[i] = value;
      result.data[i + 1] = value;
      result.data[i + 2] = value;
      result.data[i + 3] = 255;
      if (value > 0) empty = false;
    }

    if (empty) return null;

    const exportCanvas = document.createElement("canvas");
    exportCanvas.width = width;
    exportCanvas.height = height;
    exportCanvas.getContext("2d")!.putImageData(result, 0, 0);

    return await new Promise((resolve, reject) => exportCanvas.toBlob(
      (blob) => blob ? resolve(blob) : reject(new Error("Failed to encode the mask")),
      "image/png",
    ));
  }
</script>

<div class="w-full h-full relative" bind:clientWidth={containerWidth} bind:clientHeight={containerHeight}>
  <div
    class="absolute"
    style:left="{(containerWidth - natural.width * scale) / 2}px"
    style:top="{(containerHeight - natural.height * scale) / 2}px"
    style:width="{natural.width * scale}px"
    style:height="{natural.height * scale}px"
  >
    <img src={imageUrl} alt="Masked" class="absolute inset-0 w-full h-full select-none" draggable="false" />
    <canvas
      bind:this={canvas}
      class="absolute inset-0 w-full h-full opacity-50 touch-none"
      style:cursor="none"
      {onpointerdown}
      {onpointermove}
      {onpointerup}
      onpointercancel={onpointerup}
      onpointerleave={() => { cursor = null; }}
    ></canvas>
    {#if cursor}
      <div
        class="absolute pointer-events-none rounded-full border-2 -translate-x-1/2 -translate-y-1/2"
        class:border-white={mode == "brush"}
        class:border-dashed={mode == "eraser"}
        class:border-yellow-300={mode == "eraser"}
        style:left="{cursor.x}px"
        style:top="{cursor.y}px"
        style:width="{brushSize}px"
        style:height="{brushSize}px"
        style:box-shadow="0 0 0 1px rgba(0, 0, 0, 0.5)"
      ></div>
    {/if}
  </div>
  {#if error}
    <span class="absolute inset-0 grid place-items-center text-red-500 text-sm p-4">{error}</span>
  {/if}
</div>
