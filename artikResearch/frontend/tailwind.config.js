/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0d1117", panel: "#161b22", panel2: "#1c2430", line: "#30363d",
        txt: "#e6edf3", mut: "#8b949e", acc: "#1f6feb", acch: "#388bfd",
      },
    },
  },
  plugins: [],
}
