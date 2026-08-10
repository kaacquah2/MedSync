/**
 * OfflineBanner — amber strip shown when the browser loses network connectivity.
 * Auto-dismisses when connection is restored.
 */

import { Alert } from "@mantine/core";
import { IconWifi } from "@tabler/icons-react";
import { useEffect, useState } from "react";

export function OfflineBanner() {
  const [offline, setOffline] = useState(!navigator.onLine);

  useEffect(() => {
    const goOffline = () => setOffline(true);
    const goOnline  = () => setOffline(false);
    window.addEventListener("offline", goOffline);
    window.addEventListener("online",  goOnline);
    return () => {
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online",  goOnline);
    };
  }, []);

  if (!offline) return null;

  return (
    <Alert
      color="warn"
      icon={<IconWifi size={16} />}
      radius={0}
      style={{
        position: "sticky",
        /* Stick just below the fixed 60px AppShell header */
        top: "var(--app-shell-header-height, 60px)",
        zIndex: 100,
        borderRadius: 0,
        /* Escape the AppShell.Main padding so the banner spans full width */
        marginTop: "calc(-1 * var(--mantine-spacing-md))",
        marginLeft: "calc(-1 * var(--mantine-spacing-md))",
        marginRight: "calc(-1 * var(--mantine-spacing-md))",
        marginBottom: "var(--mantine-spacing-md)",
      }}
    >
      Connection lost — changes may not have saved. Retrying…
    </Alert>
  );
}
