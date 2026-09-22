import { useText } from './i18n';
import type { CvProfile } from './types';

/* How a CV is shown wherever it appears: the extracted profile, and every saved
   version of it. The headings follow the page's language and direction; the
   CV's own words carry dir="auto", so an Arabic CV lays out right to left and
   an English one left to right, whichever language the page is in. */

type Absent =
  | 'name' | 'email' | 'phone' | 'location' | 'summary' | 'experience' | 'title'
  | 'dates' | 'education' | 'graduation' | 'skills';

const en = {
  missing: (what: string) => `no ${what} in the CV`,
  absent: {
    name: 'name',
    email: 'email',
    phone: 'phone',
    location: 'location',
    summary: 'summary',
    experience: 'experience',
    title: 'title',
    dates: 'dates',
    education: 'education',
    graduation: 'graduation date',
    skills: 'skills section',
  } as Record<Absent, string>,
  present: 'Present',
  contact: 'Contact',
  name: 'Name',
  email: 'Email',
  phone: 'Phone',
  location: 'Location',
  summary: 'Summary',
  experience: 'Experience',
  education: 'Education',
  skills: 'Skills',
  certifications: 'Certifications',
  projects: 'Projects',
  languages: 'Languages',
};

const ar: typeof en = {
  missing: (what: string) => `لا يوجد ${what} في السيرة الذاتية`,
  absent: {
    name: 'اسم',
    email: 'بريد إلكتروني',
    phone: 'رقم هاتف',
    location: 'موقع',
    summary: 'ملخص',
    experience: 'خبرة',
    title: 'مسمى وظيفي',
    dates: 'تواريخ',
    education: 'تعليم',
    graduation: 'تاريخ تخرج',
    skills: 'قسم للمهارات',
  },
  present: 'حتى الآن',
  contact: 'التواصل',
  name: 'الاسم',
  email: 'البريد الإلكتروني',
  phone: 'الهاتف',
  location: 'الموقع',
  summary: 'الملخص',
  experience: 'الخبرة',
  education: 'التعليم',
  skills: 'المهارات',
  certifications: 'الشهادات',
  projects: 'المشاريع',
  languages: 'اللغات',
};

const TEXT = { en, ar };

/* An empty field is a finding, not a rendering problem. The extractor is told
   never to guess a value the CV does not state, so a blank here means the CV is
   genuinely missing it — which is what the user needs to see. */
function Missing({ what }: { what: Absent }) {
  const t = useText(TEXT);
  return <span className="empty">{t.missing(t.absent[what])}</span>;
}

export function Entities({ profile }: { profile: CvProfile }) {
  const t = useText(TEXT);
  const { contact } = profile;

  function dateRange(start: string, end: string, current: boolean) {
    if (!start && !end) return null;
    return `${start || '?'} — ${current ? t.present : end || '?'}`;
  }

  return (
    <div className="entities">
      <section>
        <h4>{t.contact}</h4>
        <dl className="contact-facts">
          <dt>{t.name}</dt>
          <dd dir="auto">{contact.name || <Missing what="name" />}</dd>
          <dt>{t.email}</dt>
          <dd dir="auto">{contact.email || <Missing what="email" />}</dd>
          <dt>{t.phone}</dt>
          <dd dir="auto">{contact.phone || <Missing what="phone" />}</dd>
          <dt>{t.location}</dt>
          <dd dir="auto">{contact.location || <Missing what="location" />}</dd>
        </dl>
        {contact.links.length > 0 && (
          <div className="chips" dir="auto">
            {contact.links.map((link) => (
              <span className="pill" key={link}>{link}</span>
            ))}
          </div>
        )}
      </section>

      <section>
        <h4>{t.summary}</h4>
        <p dir="auto">{profile.summary || <Missing what="summary" />}</p>
      </section>

      <section>
        <h4>{t.experience}</h4>
        {profile.experience.length === 0 && <Missing what="experience" />}
        {profile.experience.map((role, i) => (
          <article className="finding" key={`${role.company}-${i}`} dir="auto">
            <div className="finding-head">
              <strong>{role.title || <Missing what="title" />}</strong>
              <span className="via">
                {role.company}
                {role.location ? ` · ${role.location}` : ''}
              </span>
            </div>
            <p className="note">
              {dateRange(role.start, role.end, role.current) ?? <Missing what="dates" />}
            </p>
            <ul>
              {role.bullets.map((bullet, b) => (
                <li key={b}>{bullet}</li>
              ))}
            </ul>
          </article>
        ))}
      </section>

      <section>
        <h4>{t.education}</h4>
        {profile.education.length === 0 && <Missing what="education" />}
        {profile.education.map((edu, i) => (
          <article className="finding" key={`${edu.institution}-${i}`} dir="auto">
            <div className="finding-head">
              <strong>
                {edu.degree}
                {edu.field_of_study ? `, ${edu.field_of_study}` : ''}
              </strong>
              <span className="via">{edu.institution}</span>
            </div>
            <p className="note">
              {edu.end || <Missing what="graduation" />}
              {edu.grade ? ` · ${edu.grade}` : ''}
            </p>
          </article>
        ))}
      </section>

      <section>
        <h4>{t.skills}</h4>
        {profile.skills.length === 0 ? (
          <Missing what="skills" />
        ) : (
          <div className="chips" dir="auto">
            {profile.skills.map((skill) => (
              <span className="pill" key={skill}>{skill}</span>
            ))}
          </div>
        )}
      </section>

      {profile.certifications.length > 0 && (
        <section>
          <h4>{t.certifications}</h4>
          <div className="chips" dir="auto">
            {profile.certifications.map((cert, i) => (
              <span className="pill" key={`${cert.name}-${i}`}>
                {cert.name}
                {cert.year ? ` (${cert.year})` : ''}
              </span>
            ))}
          </div>
        </section>
      )}

      {profile.projects.length > 0 && (
        <section>
          <h4>{t.projects}</h4>
          {profile.projects.map((project, i) => (
            <article className="finding" key={`${project.name}-${i}`} dir="auto">
              <div className="finding-head">
                <strong>{project.name}</strong>
              </div>
              <p>{project.description}</p>
              {project.technologies.length > 0 && (
                <div className="chips">
                  {project.technologies.map((tech) => (
                    <span className="pill" key={tech}>{tech}</span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </section>
      )}

      {profile.languages.length > 0 && (
        <section>
          <h4>{t.languages}</h4>
          <div className="chips" dir="auto">
            {profile.languages.map((lang, i) => (
              <span className="pill" key={`${lang.name}-${i}`}>
                {lang.name}
                {lang.proficiency ? ` — ${lang.proficiency}` : ''}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
