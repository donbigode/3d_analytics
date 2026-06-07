import type { AppSettings } from "$lib/stores/settings";

export const DEFAULT_BRAND_NAME = "Sua Marca";
export const DEFAULT_BRAND_COLOR = "#111827";

export function brandName(s: AppSettings | null): string {
  return s?.business_name?.trim() || DEFAULT_BRAND_NAME;
}

export function brandTagline(s: AppSettings | null): string | null {
  return s?.business_tagline?.trim() || null;
}

export function brandColor(s: AppSettings | null): string {
  return s?.brand_color_primary?.trim() || DEFAULT_BRAND_COLOR;
}

export function brandLogoUrl(s: AppSettings | null): string | null {
  return s?.logo_path ? "/api/settings/logo" : null;
}
