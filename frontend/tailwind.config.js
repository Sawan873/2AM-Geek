/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'dark-bg': '#0f1117',
        'dark-panel': '#1a1d27',
        'dark-card': '#22253a',
        'dark-border': '#2e3148',
        'accent-blue': '#4f8ef7',
        'accent-purple': '#8b5cf6',
        'accent-green': '#10b981',
        'accent-yellow': '#f59e0b',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
