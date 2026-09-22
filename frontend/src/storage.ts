/* The two settings kept on the device: the theme and the language.

   Both were stored under `resume-analyzer-*` before the app was called
   jobFix. Renaming the keys outright would have silently dropped the choice
   of everyone who had already made one, so a read falls back to the old name
   and moves the value across the first time it finds it.

   index.html does the same thing before the first paint. This is here as
   well because it runs in places that script does not -- the demo page has
   no pre-paint script -- and because moving a key twice is harmless.

   Every access is wrapped: in a private window, or with site data blocked,
   localStorage throws rather than returning null. */

export function remembered(key: string, was: string): string | null {
  try {
    const value = localStorage.getItem(key);
    if (value !== null) return value;

    const carried = localStorage.getItem(was);
    if (carried !== null) {
      localStorage.setItem(key, carried);
      localStorage.removeItem(was);
    }
    return carried;
  } catch {
    return null;
  }
}

export function remember(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* the choice still holds for this visit */
  }
}
