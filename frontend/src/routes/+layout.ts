import { api } from "$lib/api";
import { appSettings, type AppSettings } from "$lib/stores/settings";
import { user, type Me } from "$lib/stores/user";

export const ssr = false;
export const prerender = false;
export const trailingSlash = "never";

export async function load() {
  try {
    const me = await api<NonNullable<Me>>("/auth/me");
    user.set(me);
  } catch {
    user.set(null);
  }
  try {
    const s = await api<AppSettings>("/settings");
    appSettings.set(s);
  } catch {
    appSettings.set(null);
  }
  return {};
}
