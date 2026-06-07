import { writable } from "svelte/store";

export type AppSettings = {
  business_name: string;
  business_tagline: string | null;
  logo_path: string | null;
  brand_color_primary: string;
  currency: string;
};

export const appSettings = writable<AppSettings | null>(null);
