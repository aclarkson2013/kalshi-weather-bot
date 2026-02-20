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
      keyframes: {
        "toast-in": {
          "0%": { opacity: "0", transform: "translateY(-12px) scale(0.95)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "toast-out": {
          "0%": { opacity: "1", transform: "translateY(0) scale(1)" },
          "100%": { opacity: "0", transform: "translateY(-12px) scale(0.95)" },
        },
      },
      animation: {
        "toast-in": "toast-in 0.3s ease-out",
        "toast-out": "toast-out 0.3s ease-in forwards",
      },
    },
  },
  plugins: [],
};

export default config;
