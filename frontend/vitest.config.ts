import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default defineConfig((configEnv) => {
  const baseConfig = typeof viteConfig === "function" ? viteConfig(configEnv) : viteConfig;
  return mergeConfig(
    baseConfig,
    {
      test: {
        environment: "jsdom",
        setupFiles: "./src/test/setup.ts",
        globals: true,
      },
    }
  );
});
