// backend/tailwind.config.js
const path = require('path');

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    path.join(__dirname, '..', 'frontend', 'templates', '**', '*.html'),
    path.join(__dirname, 'templates', '**', '*.html'),
    path.join(__dirname, 'apps', '**', 'templates', '**', '*.html'),
    path.join(__dirname, '..', 'frontend', 'static', 'js', '**', '*.js'),
    path.join(__dirname, 'static', 'js', '**', '*.js'),
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Instrument Serif"', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
    },
  },
  plugins: [],
};