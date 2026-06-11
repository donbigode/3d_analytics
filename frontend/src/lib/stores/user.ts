import { writable } from "svelte/store";

export type Me = { id: string; name: string; email: string; must_change_password?: boolean } | null;

export const user = writable<Me>(null);
