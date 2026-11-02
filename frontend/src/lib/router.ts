/** Opt in to React Router v7 behaviour now, so a later upgrade does not change routing. */
export const ROUTER_FUTURE_FLAGS = {
  v7_startTransition: true,
  v7_relativeSplatPath: true,
} as const
