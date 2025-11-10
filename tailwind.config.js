/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
    "./*/templates/**/*.html",
  ],
  darkMode: 'class',
  theme: {
    screens: {
      'xs': '360px',
      'sm': '640px',
      'md': '768px',
      'lg': '1024px',
      'xl': '1280px',
      '2xl': '1536px',
    },
    extend: {
      colors: {
        primary: '#800080',
        'primary-dark': '#660066',
        background: {
          light: '#ffffff',
          dark: '#121212'
        },
        text: {
          light: '#333333',
          dark: '#e0e0e0'
        },
        accent: {
          light: '#f0f0f0',
          dark: '#1e1e1e'
        },
        border: {
          light: '#E5E7EB',
          dark: '#333333'
        },
        'text-secondary': {
          light: '#6B7280',
          dark: '#808080'
        },
        'brand-purple': '#800080',
        'brand-black': '#0A0A0A',
        'brand-white': '#FFFFFF',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-in-out',
        'slide-up': 'slideUp 0.5s ease-in-out',
        'pulse': 'pulse 2s infinite',
        'scale-in': 'scaleIn 0.3s ease-out',
        'particle-move': 'particleMove 10s linear infinite',
        'faint-pulse': 'faintPulse 2s infinite',
        'spin-colors': 'spinColors 3s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' }
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' }
        },
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' }
        },
        scaleIn: {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' }
        },
        particleMove: {
          '0%': { transform: 'translate(0, 0)' },
          '100%': { transform: 'translate(50px, 50px)' },
        },
        faintPulse: {
          '0%, 100%': { transform: 'scale(1)' },
          '50%': { transform: 'scale(1.02)' }
        },
        spinColors: {
          '0%': { background: 'linear-gradient(90deg, #800080, #660066)' },
          '50%': { background: 'linear-gradient(90deg, #660066, #800080)' },
          '100%': { background: 'linear-gradient(90deg, #800080, #660066)' },
        },
      },
    }
  },
  plugins: [],
}
