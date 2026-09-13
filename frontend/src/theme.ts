import { useEffect, useState } from 'react';

/* Light or dark, remembered on this device.

   Until the user chooses, the page follows the system setting -- the
   stylesheet's prefers-color-scheme block already does that. The data-theme
   attribute on <html> only records an explicit choice, and index.html applies
   a stored one before the first paint, so a light-mode user never sees a dark
   flash on load. */
export type Theme = 'light' | 'dark';

const KEY = 'resume-analyzer-theme';

function stored(): Theme | null {
  try {
    const value = localStorage.getItem(KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null; // private windows and blocked storage: fall back to the system
  }
}

function system(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => stored() ?? system());

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  function toggle() {
    setTheme((current) => {
      const next: Theme = current === 'dark' ? 'light' : 'dark';
      try {
        localStorage.setItem(KEY, next);
      } catch {
        /* the choice still holds for this visit */
      }
      return next;
    });
  }

  return [theme, toggle];
}
