import { createContext, createElement, useContext, useLayoutEffect, useState, type ReactNode } from 'react';
import { remember, remembered } from './storage';

/* English or Arabic, remembered on this device.

   Until the user chooses, the page follows the browser's first language.
   index.html applies the stored or detected language (and its direction)
   before the first paint, so an Arabic reader never sees the page flip.

   Each component keeps its own strings as `{ en, ar }` with `ar` typed as
   `typeof en`, so a missing or misspelled Arabic entry fails the build instead
   of showing English in the middle of an Arabic page. */

export type Lang = 'en' | 'ar';

const KEY = 'jobfix-lang';
const WAS = 'resume-analyzer-lang';   // what it was called before jobFix

function stored(): Lang | null {
  const value = remembered(KEY, WAS);
  return value === 'en' || value === 'ar' ? value : null;
}

function fromBrowser(): Lang {
  if (typeof navigator === 'undefined') return 'en';
  const first = navigator.languages?.[0] ?? navigator.language ?? '';
  return first.toLowerCase().startsWith('ar') ? 'ar' : 'en';
}

/* The language as code outside React sees it. An object rather than a `let`,
   so the provider below updates a property instead of reassigning a module
   variable from inside a component. */
const store: { lang: Lang } = { lang: stored() ?? fromBrowser() };

/* For code outside React -- the API client sends it with every request, so
   the server writes its messages and the model its prose in this language. */
export function currentLang(): Lang {
  return store.lang;
}

function apply(lang: Lang) {
  const root = document.documentElement;
  root.lang = lang;
  root.dir = lang === 'ar' ? 'rtl' : 'ltr';
}

const LangContext = createContext<{ lang: Lang; setLang: (lang: Lang) => void }>({
  lang: store.lang,
  setLang: () => {},
});

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setState] = useState<Lang>(store.lang);

  /* A layout effect, not a plain one: every layout effect runs before any
     component's ordinary effects, and those are where requests start -- so
     the first request after a switch already carries the new language. */
  useLayoutEffect(() => {
    store.lang = lang;
    apply(lang);
  }, [lang]);

  function setLang(next: Lang) {
    remember(KEY, next);
    setState(next);
  }

  return createElement(LangContext.Provider, { value: { lang, setLang } }, children);
}

export function useLang(): Lang {
  return useContext(LangContext).lang;
}

export function useSetLang(): (lang: Lang) => void {
  return useContext(LangContext).setLang;
}

/* This component's strings in the current language. */
export function useText<T>(table: { en: T; ar: T }): T {
  return table[useLang()];
}

/* A counted noun in Arabic. One and two have their own forms ("تعديل واحد",
   "تعديلان"); three to ten take the plural; eleven and up the singular. */
export function arCount(
  n: number,
  forms: { one: string; two: string; few: string; many: string },
): string {
  if (n === 1) return forms.one;
  if (n === 2) return forms.two;
  if (n >= 3 && n <= 10) return `${n} ${forms.few}`;
  return `${n} ${forms.many}`;
}

/* Dates in the page's language, always Gregorian and with Western digits --
   Arabic's default locale would switch the calendar and the numerals. */
export function formatDate(iso: string, lang: Lang): string {
  return new Date(iso).toLocaleDateString(lang === 'ar' ? 'ar-u-ca-gregory-nu-latn' : undefined);
}
