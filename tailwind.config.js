/** Tailwind config for DermaCareAI. Build: `npm run build:css` (output: app/static/css/app.css). */
module.exports = {
  content: ["./app/templates/**/*.html", "./app/static/js/**/*.js"],
  // Class-based dark mode: theme.js adds `dark` to <html> from the saved choice or the OS setting.
  darkMode: "class",
  // Classes added only by JavaScript at runtime.
  safelist: ["dark", "open", "show", "dragover", "is-loading", "nav-hidden"],
  theme: {
    extend: {
      colors: {
        // Soft medical blue (clinic style). Every accent on the site uses this palette.
        brand: {
          50: "#f0f6fc", 100: "#dce9f7", 200: "#bcd5ef", 300: "#8db8e3", 400: "#5a97d3",
          500: "#3a7cc0", 600: "#2b64a3", 700: "#245085", 800: "#20436d", 900: "#1d395b", 950: "#13253d",
        },
        // Single-colour look: the old "coral" accent uses the same blue as the brand.
        coral: {
          50: "#f0f6fc", 100: "#dce9f7", 200: "#bcd5ef", 300: "#8db8e3", 400: "#5a97d3",
          500: "#3a7cc0", 600: "#2b64a3", 700: "#245085", 800: "#20436d", 900: "#1d395b",
        },
        ink: { 950: "#0b1214" },
        // Dark mode uses neutral charcoal instead of Tailwind's navy-tinted "slate", so it looks calm and printed,
        // not like a neon dashboard. 50-600 keep Tailwind's values (light mode is unchanged).
        slate: {
          50: "#f8fafc", 100: "#f1f5f9", 200: "#e2e8f0", 300: "#cbd5e1", 400: "#94a3b8", 500: "#64748b",
          600: "#475569", 700: "#3a3f45", 800: "#2a2d31", 900: "#202225", 950: "#17181a",
        },
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
