/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        ink: {
          900: '#0f172a',
          700: '#334155',
          500: '#64748b',
          400: '#94a3b8',
          300: '#cbd5e1',
          200: '#e2e8f0',
          100: '#f1f5f9',
          50:  '#f8fafc',
        },
        brand: {
          600: '#2563eb',
          500: '#3b82f6',
          100: '#dbeafe',
          50:  '#eff6ff',
        },
      },
      keyframes: {
        // Fields flash when the AI writes to them - makes it obvious in the
        // demo which fields each turn touched.
        fieldFlash: {
          '0%':   { backgroundColor: '#dbeafe', borderColor: '#3b82f6' },
          '100%': { backgroundColor: '#ffffff', borderColor: '#e2e8f0' },
        },
        rise: {
          '0%':   { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        fieldFlash: 'fieldFlash 1.6s ease-out',
        rise: 'rise 0.25s ease-out',
      },
    },
  },
  plugins: [],
}
