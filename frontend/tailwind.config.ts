import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "boz-primary": "#2563eb",
        "boz-success": "#16a34a",
        "boz-danger": "#dc2626",
        "boz-warning": "#d97706",
        "boz-neutral": "#6b7280",
      },
    },
  },
  plugins: [],
};

export default config;
