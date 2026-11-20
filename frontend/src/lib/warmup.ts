import type { Health } from "../types";

/** How long each long-poll asks the server to hold the request (server caps at 280 s). */
export const WAIT_S = 120;

/**
 * After a cold start the server is up but still loading its search model. Keep one
 * long-poll open until it is ready: besides telling the UI when to drop the notice, an
 * open request is what keeps Cloud Run's CPU allocated so the load can finish (C-030).
 * Reports every health snapshot; stops when ready, on a load failure, or after `rounds`.
 */
export async function waitUntilReady(
  fetchHealth: (waitS: number) => Promise<Health | null>,
  onHealth: (health: Health | null) => void,
  rounds = 3,
): Promise<void> {
  let health = await fetchHealth(0);
  onHealth(health);
  for (let i = 0; i < rounds && health?.warming_up; i++) {
    health = await fetchHealth(WAIT_S);
    onHealth(health);
  }
}
