import { goto } from "$app/navigation";
import { get } from "svelte/store";
import { user } from "$lib/stores/user";
import { ApiError } from "$lib/api";

/** Redirect to /login if no authenticated user is loaded. Returns true if guarded. */
export function requireAuth(): boolean {
  if (!get(user)) {
    goto("/login");
    return true;
  }
  return false;
}

/** Handle errors that should bounce the user to /login (401). */
export function handleApiError(err: unknown): void {
  if (err instanceof ApiError && err.status === 401) {
    user.set(null);
    goto("/login");
  }
}
