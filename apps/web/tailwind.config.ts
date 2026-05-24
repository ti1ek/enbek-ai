import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Vellum palette (claude.ai)
        vellum: "#faf9f5",   // page background
        ink: "#141413",      // primary text
        onyx: "#1f1e1d",     // borders, accents
        graphite: "#3d3d3a", // secondary text
        dusty: "#73726c",    // tertiary text, labels
        stone: "#9c9a92",    // placeholder, inactive icons
        parchment: "#dedcd1",// borders, dividers
        snow: "#ffffff",     // input bg, surfaces
        azure: "#ccdbe8",    // subtle accent border
        terra: "#5f7a5f",    // accent (sage green)
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["var(--font-lora)", "Georgia", "Cambria", "serif"],
        nunito: ["var(--font-nunito)", "sans-serif"],
      },
      fontSize: {
        caption:      ["11px", { lineHeight: "1.45" }],
        body:         ["14px", { lineHeight: "1.5"  }],
        base:         ["15px", { lineHeight: "1.6"  }],
        subheading:   ["18px", { lineHeight: "1.33" }],
        "heading-sm": ["24px", { lineHeight: "1.33" }],
        heading:      ["30px", { lineHeight: "1.2"  }],
        display:      ["56px", { lineHeight: "1.2"  }],
      },
      borderRadius: {
        DEFAULT: "9.6px",
        card: "16px",
        xl: "24px",
        "2xl": "32px",
      },
      boxShadow: {
        sm:   "0 1px 3px rgba(31,30,29,0.06)",
        card: "0 2px 8px rgba(31,30,29,0.06), 0 0 0 1px rgba(31,30,29,0.04)",
      },
      maxWidth: {
        content: "740px",
      },
      keyframes: {
        "fade-up": {
          "0%":   { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)"    },
        },
        "typing-bounce": {
          "0%, 80%, 100%": { transform: "translateY(0)",   opacity: "0.35" },
          "40%":            { transform: "translateY(-4px)", opacity: "1"   },
        },
      },
      animation: {
        "fade-up":       "fade-up 0.4s cubic-bezier(0.22, 1, 0.36, 1) both",
        "typing-bounce": "typing-bounce 1.3s infinite ease-in-out",
      },
    },
  },
  plugins: [],
};

export default config;
