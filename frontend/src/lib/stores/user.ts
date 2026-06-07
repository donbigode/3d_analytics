import { writable } from "svelte/store";

export type Me = { id: string; name: string; email: string } | null;

export const user = writable<Me>(null);
