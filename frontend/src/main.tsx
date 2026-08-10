import "@mantine/core/styles.css";
import "@mantine/charts/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/notifications/styles.css";
import "./global.css";

import { MantineProvider, createTheme } from "@mantine/core";
import { ModalsProvider }               from "@mantine/modals";
import { Notifications }                from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode }                   from "react";
import { createRoot }                   from "react-dom/client";
import { BrowserRouter }                from "react-router-dom";
import { App }                          from "./App";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: true,
    },
    mutations: {
      retry: false,
    },
  },
});

const theme = createTheme({
  primaryColor: "medsync",
  fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
  fontFamilyMonospace: "'IBM Plex Mono', monospace",
  defaultRadius: "14px",
  focusRing: "auto",
  cursorType: "pointer",
  headings: {
    fontFamily: "'Bricolage Grotesque', sans-serif",
    fontWeight: "700",
    sizes: {
      h1: { fontSize: "2rem",    lineHeight: "1.2" },
      h2: { fontSize: "1.5rem",  lineHeight: "1.3" },
      h3: { fontSize: "1.25rem", lineHeight: "1.35" },
      h4: { fontSize: "1.1rem",  lineHeight: "1.4" },
      h5: { fontSize: "0.95rem", lineHeight: "1.45" },
    },
  },
  primaryShade: { light: 5, dark: 4 },
  colors: {
    // Redesign primary Brand Accent teal scale
    medsync: [
      "#eef9f7", // 0 — light teal bg
      "#d5f0eb", // 1
      "#ade1d7", // 2
      "#80cdc0", // 3
      "#4fb4a6", // 4
      "#177E6F", // 5 — PRIMARY Brand Accent teal
      "#0f6a5d", // 6 — hover state
      "#0b5147", // 7
      "#083b33", // 8
      "#04221d", // 9
    ],
    // Clinical success green
    clinical: [
      "#e6fcf5", "#c3fae8", "#96f2d7", "#63e6be",
      "#38d9a9", "#2e8b6f", "#12b886", "#0ca678", // 4 is #38d9a9 (bright green in dark mode)
      "#099268", "#087f5b",
    ],
    // Override Mantine default green palette for high dark-mode contrast
    green: [
      "#e6fcf5", "#c3fae8", "#96f2d7", "#63e6be",
      "#38d9a9", "#2e8b6f", "#12b886", "#0ca678",
      "#099268", "#087f5b",
    ],
    // Danger red
    danger: [
      "#fee2e2", "#fecaca", "#fca5a5", "#f87171",
      "#ef4444", "#b4452e", "#b91c1c", "#991b1b",
      "#7f1d1d", "#450a0a",
    ],
    // Warning amber
    warn: [
      "#fef3c7", "#fde68a", "#fcd34d", "#fbbf24",
      "#f59e0b", "#c7871f", "#b45309", "#92400e",
      "#78350f", "#451a03",
    ],
  },
  components: {
    Card: {
      defaultProps: {
        shadow: "none",
        withBorder: true,
        radius: "14px",
      },
    },
    Button: {
      defaultProps: {
        radius: "md",
        fw: 600,
      },
      styles: {
        root: {
          height: 36,
          fontSize: 14,
        },
      },
    },
    TextInput: {
      styles: {
        input: {
          height: 40,
          fontSize: 14,
        },
      },
    },
    Select: {
      styles: {
        input: {
          height: 40,
          fontSize: 14,
        },
      },
    },
    Table: {
      styles: {
        th: {
          fontSize: 12,
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        },
      },
    },
    Textarea: {
      styles: {
        input: {
          fontSize: 14,
        },
      },
    },
    Paper: {
      defaultProps: {
        radius: "md",
      },
    },
    Badge: {
      defaultProps: {
        radius: "sm",
        fw: 600,
      },
    },
    Modal: {
      defaultProps: {
        centered: true,
        radius: "md",
      },
    },
    Tabs: {
      styles: {
        tab: {
          fontWeight: 500,
        },
      },
    },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("No #root element found");

createRoot(root).render(
  <StrictMode>
    <BrowserRouter basename={import.meta.env.DEV ? "/" : "/spa"}>
      <QueryClientProvider client={queryClient}>
        <MantineProvider theme={theme} defaultColorScheme="light">
          <ModalsProvider>
            <Notifications position="bottom-right" zIndex={9999} />
            <App />
          </ModalsProvider>
        </MantineProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>
);
