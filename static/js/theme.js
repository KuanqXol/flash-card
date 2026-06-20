/**
 * FlashVocab V2 — Theme Manager
 * Handles dark/light mode toggle with localStorage persistence.
 */
(function() {
  'use strict';

  const STORAGE_KEY = 'flashvocab-theme';
  const DARK = 'dark';
  const LIGHT = 'light';

  // Read saved preference or system preference
  function getPreferredTheme() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === DARK || saved === LIGHT) return saved;

    // Check system preference
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return DARK;
    }
    return LIGHT;
  }

  // Apply theme to DOM
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);

    // Update toggle button icon if exists
    const toggleIcons = document.querySelectorAll('.theme-toggle-icon');
    toggleIcons.forEach(icon => {
      if (theme === DARK) {
        icon.innerHTML = '<i class="ph ph-sun"></i>';
      } else {
        icon.innerHTML = '<i class="ph ph-moon"></i>';
      }
    });

    const toggleLabels = document.querySelectorAll('.theme-toggle-label');
    toggleLabels.forEach(label => {
      label.textContent = theme === DARK ? 'Light Mode' : 'Dark Mode';
    });
  }

  // Toggle between themes
  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || LIGHT;
    const next = current === DARK ? LIGHT : DARK;
    applyTheme(next);
  }

  // Initialize on DOM ready
  function init() {
    const theme = getPreferredTheme();
    applyTheme(theme);

    // Listen for system theme changes
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem(STORAGE_KEY)) {
          applyTheme(e.matches ? DARK : LIGHT);
        }
      });
    }
  }

  // Apply theme immediately (before DOM ready) to prevent flash
  const earlyTheme = getPreferredTheme();
  document.documentElement.setAttribute('data-theme', earlyTheme);

  // Full init on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose globally
  window.FlashVocabTheme = {
    toggle: toggleTheme,
    set: applyTheme,
    get: () => document.documentElement.getAttribute('data-theme') || LIGHT
  };
})();
