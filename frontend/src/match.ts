/* How a match is described, shared by the two places that describe one: the
   full ring on a finished analysis and the badge on a search result.

   They band the same words onto two different scales, and the scales are not
   interchangeable:

   - the analysis score is out of 100, computed in Python from the model's
     evidence, and a good CV against a good posting really does reach the 80s;
   - a search result has no analysis behind it. All that is known for free is
     how much of the posting's own vocabulary the CV carries, and on a real
     advert -- benefits block stripped -- a direct hit lands around 40%.

   Banding both on the same thresholds would label every search result weak.
   So the thresholds differ and the words do not. */

export type Band = 'strong' | 'good' | 'fair' | 'weak';

/* The analyst's own thresholds: 80 is the point past which what is left is
   polish. */
export function scoreBand(score: number): Band {
  if (score >= 80) return 'strong';
  if (score >= 60) return 'good';
  if (score >= 40) return 'fair';
  return 'weak';
}

/* Calibrated against real postings rather than chosen round: measured over
   full-length adverts, a role matching the CV closely covers about 40% of its
   vocabulary, an adjacent role about 20%, and an unrelated one under 5%. */
export function coverageBand(coverage: number): Band {
  if (coverage >= 0.35) return 'strong';
  if (coverage >= 0.22) return 'good';
  if (coverage >= 0.12) return 'fair';
  return 'weak';
}

const en = {
  strong: 'Strong match',
  good: 'Good match',
  fair: 'Fair match',
  weak: 'Weak match',
} as Record<Band, string>;

const ar: typeof en = {
  strong: 'تطابق قوي',
  good: 'تطابق جيد',
  fair: 'تطابق متوسط',
  weak: 'تطابق ضعيف',
};

export const BAND_TEXT = { en, ar };
