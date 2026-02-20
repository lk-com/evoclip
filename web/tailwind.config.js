/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,ts}"],
  theme: {
    extend: {
      colors: {
        primary: "#080818",
        secondary: "#0F0F2E",
        "secondary-light": "#1A1840",
        cta: "#E11D48",
        "cta-light": "#F43F5E",
        "cta-dark": "#BE123C",
        background: "#000000",
        surface: "rgba(15, 15, 46, 0.65)",
        "surface-hover": "rgba(26, 24, 64, 0.85)",
        "surface-bright": "rgba(30, 27, 75, 0.4)",
        accent: "#7C3AED",
        "accent-light": "#A78BFA",
      },
      fontFamily: {
        sans: ["Plus Jakarta Sans", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      boxShadow: {
        glass: "0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.05)",
        glow: "0 0 24px rgba(225, 29, 72, 0.35), 0 0 48px rgba(225, 29, 72, 0.1)",
        "glow-sm": "0 0 12px rgba(225, 29, 72, 0.25)",
        "glow-purple": "0 0 24px rgba(124, 58, 237, 0.3)",
        card: "0 4px 24px rgba(0, 0, 0, 0.5)",
        "card-hover": "0 8px 40px rgba(0, 0, 0, 0.6), 0 0 20px rgba(225, 29, 72, 0.1)",
        inset: "inset 0 1px 0 rgba(255,255,255,0.06)",
      },
      backdropBlur: {
        glass: "16px",
        heavy: "24px",
      },
      borderColor: {
        DEFAULT: "rgba(255,255,255,0.08)",
      },
      animation: {
        "fade-in": "fadeIn 0.6s ease-out both",
        "slide-up": "slideUp 0.6s ease-out both",
        "slide-down": "slideDown 0.4s ease-out both",
        "scale-in": "scaleIn 0.3s ease-out both",
        "glow-pulse": "glowPulse 3s ease-in-out infinite",
        "gradient-shift": "gradientShift 6s ease infinite",
        "progress-bar": "progressBar 1.5s ease-in-out infinite",
        pulse: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "spin-slow": "spin 3s linear infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(24px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideDown: {
          "0%": { opacity: "0", transform: "translateY(-12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        glowPulse: {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "0.8" },
        },
        gradientShift: {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        progressBar: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(400%)" },
        },
      },
      spacing: {
        "18": "4.5rem",
        "88": "22rem",
        "128": "32rem",
      },
      borderRadius: {
        "4xl": "2rem",
      },
    },
  },
  plugins: [],
};
