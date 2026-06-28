/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#1f6feb", 600: "#1f6feb", 700: "#1a5fd0" },
      },
    },
  },
  plugins: [],
};
