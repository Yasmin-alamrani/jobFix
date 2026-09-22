/* The wait, given a shape. A CV being read, a bar that keeps moving, and the
   sentence saying what is happening -- the three things a person needs while a
   fetch and a model call take their time.

   The bar is deliberately indeterminate. We cannot know how long a posting
   takes to fetch, and a progress bar that claims 70% and then sits there is a
   worse lie than one that only says "still working". */
export default function Matching({ label }: { label: string }) {
  return (
    <div className="matching" role="status" aria-live="polite">
      <svg className="matching-doc" viewBox="0 0 72 78" aria-hidden="true">
        {/* the sheet behind, just showing at the edge */}
        <rect className="sheet back" x="7" y="12" width="20" height="56" rx="4" />
        {/* the page under inspection, corner turned down */}
        <path
          className="sheet"
          d="M22 6h27l13 13v49a5 5 0 0 1-5 5H22a5 5 0 0 1-5-5V11a5 5 0 0 1 5-5z"
        />
        <path className="fold" d="M49 6v13h13" />
        <rect className="chip" x="26" y="26" width="11" height="11" rx="2.5" />
        <path className="line short" d="M42 31h12" />
        <path className="line" d="M26 46h28" />
        <path className="line" d="M26 54h28" />
        <path className="line short" d="M26 62h17" />
      </svg>

      <div className="matching-track">
        <i />
      </div>

      <p className="matching-label" dir="auto">
        {label}
      </p>
    </div>
  );
}
