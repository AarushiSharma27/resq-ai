/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: { 950: '#060b17', 900: '#0a1020', 850: '#0e1629', 800: '#121c33', 700: '#1b2744', 600: '#26345a' },
        emergency: '#ef4444',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      keyframes: {
        pulsedot: { '0%,100%': { opacity: '1' }, '50%': { opacity: '0.35' } },
        slidein: { from: { opacity: '0', transform: 'translateY(4px)' }, to: { opacity: '1', transform: 'none' } },
      },
      animation: { pulsedot: 'pulsedot 1.6s ease-in-out infinite', slidein: 'slidein .25s ease-out' },
    },
  },
  plugins: [],
};
