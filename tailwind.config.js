/** Tailwind config for DermaCareAI. Build: `npm run build:css` (output: app/static/css/app.css). */
module.exports = {
  content: ["./app/templates/**/*.html", "./app/static/js/**/*.js"],
  // Class-based dark mode: theme.js adds `dark` to <html> from the saved choice or the OS setting.
  darkMode: "class",
  // Classes added only by JavaScript at runtime.
  safelist: ["dark", "open", "show", "dragover", "is-loading"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#effaf8", 100: "#d7f2ec", 200: "#b0e4da", 300: "#7fcfc0", 400: "#4db5a3",
          500: "#2f9886", 600: "#237a6c", 700: "#1f6358", 800: "#1c4f47", 900: "#19423c", 950: "#0a2622",
        },
        coral: {
          50: "#fff5f1", 100: "#ffe7de", 200: "#ffcdbd", 300: "#ffa98f", 400: "#fb8360",
          500: "#ef6640", 600: "#d84e2a", 700: "#b43d20", 800: "#91341f", 900: "#772f1e",
        },
        ink: { 950: "#0b1214" },
      },
      fontFamily: {
        sans: ['"Segoe UI Variable Text"', '"Segoe UI"', "system-ui", "-apple-system", "Roboto",
               '"Helvetica Neue"', "Arial", "sans-serif"],
        display: ['"Segoe UI Variable Display"', '"Segoe UI"', "system-ui", "-apple-system",
                  "Roboto", "sans-serif"],
        mono: ["Consolas", '"Cascadia Mono"', "Menlo", "monospace"],
      },
      maxWidth: { content: "1160px", reading: "680px" },
      boxShadow: {
        card: "0 1px 2px rgb(15 23 42 / 0.04), 0 4px 16px rgb(15 23 42 / 0.06)",
        lift: "0 2px 4px rgb(15 23 42 / 0.05), 0 12px 32px rgb(15 23 42 / 0.10)",
      },
    },
  },
  plugins: [],
};
