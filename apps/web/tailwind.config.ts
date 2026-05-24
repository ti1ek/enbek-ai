import type { Config } from "tailwindcss";

/**
 * Дизайн-токены стиля Stripe (styles.refero.design, тема Light).
 * Светлый «холст» + единый фиолетовый CTA + оранжевый/зелёный акценты.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Фоны
        page: "#f8fafd",
        surface: "#ffffff",
        powder: "#e5edf5",
        porcelain: "#f8fafd",
        // Текст
        ink: "#061b31",      // midnight ink — основной текст
        slate: "#50617a",    // вторичный текст
        ghost: "#64748d",    // placeholder / inactive
        stone: "#d8d6df",    // бордеры
        // Бренд / CTA
        violet: {
          DEFAULT: "#533afd",
          soft: "#8087ff",
          washed: "#b9b9f9",
        },
        // Цветные акценты
        orange: "#ff6118",
        leaf: "#81b81a",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      fontSize: {
        // role: [size, { lineHeight, letterSpacing }]
        caption: ["11px", { lineHeight: "1.45", letterSpacing: "0.03px" }],
        body: ["14px", { lineHeight: "1.4", letterSpacing: "0.003px" }],
        subheading: ["18px", { lineHeight: "1.25", letterSpacing: "-0.009em" }],
        "heading-sm": ["22px", { lineHeight: "1.2", letterSpacing: "-0.01em" }],
        heading: ["32px", { lineHeight: "1.15", letterSpacing: "-0.02em" }],
        "heading-lg": ["44px", { lineHeight: "1.1", letterSpacing: "-0.025em" }],
        display: ["56px", { lineHeight: "1.07", letterSpacing: "-0.03em" }],
      },
      borderRadius: {
        DEFAULT: "4px", // кнопки, инпут
        card: "6px",
      },
      boxShadow: {
        sm: "rgba(23, 23, 23, 0.06) 0px 3px 6px 0px",
        card: "rgba(50, 50, 93, 0.12) 0px 16px 32px 0px",
        glow: "rgba(0, 0, 0, 0.2) 0px 0px 32px 8px",
      },
      backgroundImage: {
        // Stripe «Sunburst» — для акцентов и hero
        sunburst:
          "linear-gradient(90deg, #7232f1 3.13%, #fb76fa 50%, #ffcf5e)",
        "sunburst-soft":
          "linear-gradient(90deg, rgba(114,50,241,0.10), rgba(251,118,250,0.10), rgba(255,207,94,0.10))",
      },
      maxWidth: {
        content: "720px",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "typing-bounce": {
          "0%, 80%, 100%": { transform: "translateY(0)", opacity: "0.35" },
          "40%": { transform: "translateY(-5px)", opacity: "1" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.45s cubic-bezier(0.22, 1, 0.36, 1) both",
        "typing-bounce": "typing-bounce 1.3s infinite ease-in-out",
      },
    },
  },
  plugins: [],
};

export default config;
