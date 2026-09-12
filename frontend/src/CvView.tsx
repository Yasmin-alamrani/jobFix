import type { CvProfile } from './types';

/* How a CV is shown wherever it appears: the extracted profile, and every saved
   version of it. `dir="auto"` lets an Arabic CV lay out right to left. */

/* An empty field is a finding, not a rendering problem. The extractor is told
   never to guess a value the CV does not state, so a blank here means the CV is
   genuinely missing it — which is what the user needs to see. */
function Missing({ what }: { what: string }) {
  return <span className="empty">no {what} in the CV</span>;
}

function dateRange(start: string, end: string, current: boolean) {
  if (!start && !end) return null;
  return `${start || '?'} — ${current ? 'Present' : end || '?'}`;
}

export function Entities({ profile }: { profile: CvProfile }) {
  const { contact } = profile;
  return (
    <div className="entities" dir="auto">
      <section>
        <h4>Contact</h4>
        <dl className="contact-facts">
          <dt>Name</dt>
          <dd>{contact.name || <Missing what="name" />}</dd>
          <dt>Email</dt>
          <dd>{contact.email || <Missing what="email" />}</dd>
          <dt>Phone</dt>
          <dd>{contact.phone || <Missing what="phone" />}</dd>
          <dt>Location</dt>
          <dd>{contact.location || <Missing what="location" />}</dd>
        </dl>
        {contact.links.length > 0 && (
          <div className="chips">
            {contact.links.map((link) => (
              <span className="pill" key={link}>{link}</span>
            ))}
          </div>
        )}
      </section>

      <section>
        <h4>Summary</h4>
        <p>{profile.summary || <Missing what="summary" />}</p>
      </section>

      <section>
        <h4>Experience</h4>
        {profile.experience.length === 0 && <Missing what="experience" />}
        {profile.experience.map((role, i) => (
          <article className="finding" key={`${role.company}-${i}`}>
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
        <h4>Education</h4>
        {profile.education.length === 0 && <Missing what="education" />}
        {profile.education.map((edu, i) => (
          <article className="finding" key={`${edu.institution}-${i}`}>
            <div className="finding-head">
              <strong>
                {edu.degree}
                {edu.field_of_study ? `, ${edu.field_of_study}` : ''}
              </strong>
              <span className="via">{edu.institution}</span>
            </div>
            <p className="note">
              {edu.end || <Missing what="graduation date" />}
              {edu.grade ? ` · ${edu.grade}` : ''}
            </p>
          </article>
        ))}
      </section>

      <section>
        <h4>Skills</h4>
        {profile.skills.length === 0 ? (
          <Missing what="skills section" />
        ) : (
          <div className="chips">
            {profile.skills.map((skill) => (
              <span className="pill" key={skill}>{skill}</span>
            ))}
          </div>
        )}
      </section>

      {profile.certifications.length > 0 && (
        <section>
          <h4>Certifications</h4>
          <div className="chips">
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
          <h4>Projects</h4>
          {profile.projects.map((project, i) => (
            <article className="finding" key={`${project.name}-${i}`}>
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
          <h4>Languages</h4>
          <div className="chips">
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
