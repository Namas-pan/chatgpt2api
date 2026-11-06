/**
 * 图片格式识别：让下载/预览按"原始素材"的格式走。
 *
 * 上游返回的图片不再只有 PNG（现在还有 GIF、SVG 等），如果一律按 image/png
 * 处理和命名，动图会丢失动画、矢量图会被错标成位图。这里统一按文件头判断真实格式。
 */

export type ImageFormat = {
  ext: string;
  mime: string;
};

export const IMAGE_FORMATS = {
  png: { ext: "png", mime: "image/png" },
  jpeg: { ext: "jpg", mime: "image/jpeg" },
  gif: { ext: "gif", mime: "image/gif" },
  webp: { ext: "webp", mime: "image/webp" },
  svg: { ext: "svg", mime: "image/svg+xml" },
} as const satisfies Record<string, ImageFormat>;

const FORMAT_BY_MIME: Record<string, ImageFormat> = {
  "image/png": IMAGE_FORMATS.png,
  "image/jpeg": IMAGE_FORMATS.jpeg,
  "image/jpg": IMAGE_FORMATS.jpeg,
  "image/gif": IMAGE_FORMATS.gif,
  "image/webp": IMAGE_FORMATS.webp,
  "image/svg+xml": IMAGE_FORMATS.svg,
};

const FORMAT_BY_EXTENSION: Record<string, ImageFormat> = {
  png: IMAGE_FORMATS.png,
  jpg: IMAGE_FORMATS.jpeg,
  jpeg: IMAGE_FORMATS.jpeg,
  gif: IMAGE_FORMATS.gif,
  webp: IMAGE_FORMATS.webp,
  svg: IMAGE_FORMATS.svg,
};

export function formatFromMimeType(value: string | null | undefined): ImageFormat | null {
  const mime = String(value || "").split(";")[0].trim().toLowerCase();
  return FORMAT_BY_MIME[mime] ?? null;
}

export function formatFromExtension(value: string | null | undefined): ImageFormat | null {
  const extension = String(value || "").trim().replace(/^\./, "").toLowerCase();
  return FORMAT_BY_EXTENSION[extension] ?? null;
}

/** 从 URL 路径后缀判断格式（忽略 query/hash）。 */
export function formatFromUrl(url: string | null | undefined): ImageFormat | null {
  const text = String(url || "").trim();
  if (!text) {
    return null;
  }
  try {
    const pathname = new URL(text, "http://local.invalid").pathname;
    const match = /\.([a-z0-9]+)$/i.exec(pathname);
    return match ? formatFromExtension(match[1]) : null;
  } catch {
    const match = /\.([a-z0-9]+)(?:[?#].*)?$/i.exec(text);
    return match ? formatFromExtension(match[1]) : null;
  }
}

function hasPrefix(bytes: Uint8Array, prefix: number[]): boolean {
  if (bytes.length < prefix.length) {
    return false;
  }
  return prefix.every((value, index) => bytes[index] === value);
}

/** 按文件头识别真实格式。 */
export function detectImageFormat(bytes: Uint8Array): ImageFormat | null {
  if (!bytes.length) {
    return null;
  }
  if (hasPrefix(bytes, [0x89, 0x50, 0x4e, 0x47])) {
    return IMAGE_FORMATS.png;
  }
  if (hasPrefix(bytes, [0xff, 0xd8, 0xff])) {
    return IMAGE_FORMATS.jpeg;
  }
  // GIF87a / GIF89a
  if (hasPrefix(bytes, [0x47, 0x49, 0x46])) {
    return IMAGE_FORMATS.gif;
  }
  // RIFF....WEBP
  if (hasPrefix(bytes, [0x52, 0x49, 0x46, 0x46]) && bytes.length >= 12) {
    if (bytes[8] === 0x57 && bytes[9] === 0x45 && bytes[10] === 0x42 && bytes[11] === 0x50) {
      return IMAGE_FORMATS.webp;
    }
  }
  // SVG 是文本，可能带 BOM、空白、XML 声明或注释
  try {
    const head = new TextDecoder("utf-8", { fatal: false }).decode(bytes.slice(0, 2048));
    if (head.toLowerCase().includes("<svg")) {
      return IMAGE_FORMATS.svg;
    }
  } catch {
    return null;
  }
  return null;
}

/** 从 base64 字符串识别格式（只看开头一小段，不整段解码）。 */
export function detectImageFormatFromBase64(value: string | null | undefined): ImageFormat | null {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
  // SVG 需要看到 <svg，最多取 4KB base64（约 3KB 原文）
  const sample = text.length > 4096 ? text.slice(0, 4096) : text;
  const usable = sample.slice(0, sample.length - (sample.length % 4));
  if (!usable) {
    return null;
  }
  try {
    const binary = atob(usable);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return detectImageFormat(bytes);
  } catch {
    return null;
  }
}

/** 从任意图片 src（blob:/data:/http）解析真实格式，用于下载时决定扩展名。 */
export async function resolveImageFormatFromSrc(src: string | null | undefined): Promise<ImageFormat | null> {
  const text = String(src || "").trim();
  if (!text) {
    return null;
  }
  if (text.startsWith("data:")) {
    const comma = text.indexOf(",");
    if (comma < 0) {
      return null;
    }
    const header = text.slice(5, comma);
    if (header.includes(";base64")) {
      return detectImageFormatFromBase64(text.slice(comma + 1));
    }
    return formatFromMimeType(header.split(";")[0]);
  }
  const fromUrl = formatFromUrl(text);
  try {
    const response = await fetch(text);
    if (!response.ok) {
      return fromUrl;
    }
    const blob = await response.blob();
    const bytes = new Uint8Array(await blob.arrayBuffer());
    return detectImageFormat(bytes) || formatFromMimeType(blob.type) || fromUrl;
  } catch {
    return fromUrl;
  }
}
