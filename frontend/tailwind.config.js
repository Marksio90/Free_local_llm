/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        dark: {
          900: "#0a0a0f",
          800: "#111118",
          700: "#1a1a24",
          600: "#22222e",
          500: "#2d2d3d",
        },
        accent: {
          500: "#6366f1",
          400: "#818cf8",
          300: "#a5b4fc",
        },
      },
    },
  },
  plugins: [],
};
