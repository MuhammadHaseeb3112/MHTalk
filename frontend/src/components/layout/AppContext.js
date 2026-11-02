import { createContext, useContext } from "react";

/**
 * Navigation/UI actions shared across the app shell:
 *   openRoom(id), closeRoom(), setSection(name),
 *   pushPanel(name, props), popPanel(), resetPanels(),
 *   openDrawer(type, payload), closeDrawer(), openMedia()
 * plus ``section`` and ``compact`` (phone/tablet layout, <= 900px).
 */
export const AppContext = createContext(null);

export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used inside MainLayout");
  return value;
}
