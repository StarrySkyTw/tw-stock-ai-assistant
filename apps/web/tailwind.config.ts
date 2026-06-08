import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "rgb(var(--color-ink) / <alpha-value>)",
        muted: "rgb(var(--color-muted) / <alpha-value>)",
        line: "rgb(var(--color-line) / <alpha-value>)",
        paper: "rgb(var(--color-paper) / <alpha-value>)",
        panel: "rgb(var(--color-panel) / <alpha-value>)",
        control: "rgb(var(--color-control) / <alpha-value>)",
        gain: "rgb(var(--color-gain) / <alpha-value>)",
        warn: "rgb(var(--color-warn) / <alpha-value>)",
        loss: "rgb(var(--color-loss) / <alpha-value>)"
      }
    }
  },
  plugins: []
};

export default config;
