/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Sora", "system-ui", "sans-serif"],
        body: ["Manrope", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      colors: {
        void: "#05070d",
        surface: "#0c1120",
        "surface-2": "#121a2e",
        "surface-3": "#182238",
        border: "rgba(148,163,184,0.12)",
        "border-hover": "rgba(148,163,184,0.24)",
        ink: "#e7eaf4",
        "ink-dim": "#9aa3b8",
        "ink-mute": "#5c6480",
        blue: { DEFAULT: "#4d7fff", 400: "#6b93ff", 500: "#4d7fff", 600: "#3862e0" },
        violet: { DEFAULT: "#9b6bff", 400: "#ac83ff", 500: "#9b6bff", 600: "#7d4de0" },
        ok: { DEFAULT: "#34d399", 500: "#34d399", 600: "#22b485" },
        warn: { DEFAULT: "#f5a742", 500: "#f5a742", 600: "#d98a24" },
        bad: { DEFAULT: "#f2617a", 500: "#f2617a", 600: "#d94363" },
      },
      backgroundImage: {
        "grad-brand": "linear-gradient(135deg, #4d7fff 0%, #9b6bff 100%)",
        "grad-radial-hero":
          "radial-gradient(60% 60% at 75% 20%, rgba(77,127,255,0.18) 0%, rgba(155,107,255,0.10) 45%, rgba(5,7,13,0) 75%)",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(77,127,255,0.25), 0 8px 30px -8px rgba(77,127,255,0.35)",
        "glow-violet": "0 0 0 1px rgba(155,107,255,0.25), 0 8px 30px -8px rgba(155,107,255,0.35)",
        card: "0 1px 0 rgba(255,255,255,0.02) inset, 0 12px 30px -18px rgba(0,0,0,0.6)",
      },
      keyframes: {
        "pulse-live": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(52,211,153,0.55)" },
          "70%": { boxShadow: "0 0 0 6px rgba(52,211,153,0)" },
        },
        "rise-in": {
          from: { opacity: 0, transform: "translateY(10px)" },
          to: { opacity: 1, transform: "translateY(0)" },
        },
        shimmer: {
          from: { backgroundPosition: "-400px 0" },
          to: { backgroundPosition: "400px 0" },
        },
      },
      animation: {
        "pulse-live": "pulse-live 2s cubic-bezier(0.4,0,0.6,1) infinite",
        "rise-in": "rise-in 0.45s cubic-bezier(0.16,1,0.3,1) both",
        shimmer: "shimmer 1.6s linear infinite",
      },
    },
  },
  plugins: [],
};
