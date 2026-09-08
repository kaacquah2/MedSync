import { useState, useEffect, useCallback } from "react";
import { flushSync } from "react-dom";

/**
 * Hook to dynamically mount print-only components into the DOM only
 * during active print lifecycle events (beforeprint -> afterprint),
 * and purge them immediately when printing completes or cancels.
 *
 * This mitigates hidden-DOM PHI leaks where sensitive medical records
 * are permanently serialized in the DOM tree and merely hidden with CSS.
 */
export function useIsPrinting() {
  const [isPrinting, setIsPrinting] = useState(false);

  useEffect(() => {
    const handleBeforePrint = () => {
      flushSync(() => {
        setIsPrinting(true);
      });
    };

    const handleAfterPrint = () => {
      setIsPrinting(false);
    };

    window.addEventListener("beforeprint", handleBeforePrint);
    window.addEventListener("afterprint", handleAfterPrint);

    return () => {
      window.removeEventListener("beforeprint", handleBeforePrint);
      window.removeEventListener("afterprint", handleAfterPrint);
    };
  }, []);

  const triggerPrint = useCallback(() => {
    // Synchronously mount print elements in DOM before browser captures view
    flushSync(() => {
      setIsPrinting(true);
    });

    try {
      window.print();
    } finally {
      // Ensure DOM is unmounted and purged even if afterprint is delayed or mocked
      setIsPrinting(false);
    }
  }, []);

  return { isPrinting, triggerPrint };
}
