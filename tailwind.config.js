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
        // Flat, single-colour look: the old orange "coral" accent now uses the same green as the brand.
        coral: {
          50: "#effaf8", 100: "#d7f2ec", 200: "#b0e4da", 300: "#7fcfc0", 400: "#4db5a3",
          500: "#2f9886", 600: "#237a6c", 700: "#1f6358", 800: "#1c4f47", 900: "#19423c",
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
      // Flat design: cards use a thin border, not shadows. "lift" is kept only for the phone menu.
      boxShadow: {
        sm: "none",
        card: "none",
        lift: "0 8px 24px rgb(15 23 42 / 0.12)",
      },
      borderRadius: { "2xl": "0.75rem", "3xl": "1rem" },
    },
  },
  plugins: [],
};
