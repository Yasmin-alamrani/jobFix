"""The Arabic catalogue: every message the code writes, and its translation.

Keys are the English exactly as the code produces it. A message built from
parts is a pattern: {name} matches any text, and a slot named t_* holds a
message of its own that is translated in turn. `tests/test_i18n.py` runs the
code that produces these messages and fails on any that comes out in English.

Placeholders such as [add number] and names such as GEMINI_API_KEY, backend/.env
and robots.txt stay as they are: they are things to type or find, not words.
"""
from __future__ import annotations

EXACT: dict[str, str] = {
    # --- labels ---------------------------------------------------------------
    "ATS parseability": "قابلية القراءة في أنظمة التوظيف",
    "Keyword & skill match": "تطابق الكلمات المفتاحية والمهارات",
    "Experience & seniority fit": "ملاءمة الخبرة والمستوى الوظيفي",
    "Formatting & structure": "التنسيق والبنية",
    "Technology": "التقنية",
    "Banking": "البنوك",
    "Fintech": "التقنية المالية",
    "Energy": "الطاقة",
    "Healthcare": "الرعاية الصحية",
    "Consulting": "الاستشارات",
    "Government & public sector": "الحكومة والقطاع العام",
    "Other": "أخرى",
    "Core skills": "المهارات الأساسية",
    "Evidenced experience": "الخبرة المُثبتة",
    "Title alignment": "توافق المسميات الوظيفية",
    "Original": "الأصلية",
    "Tailored CV": "سيرة ذاتية مخصّصة",
    "Untitled role": "دور بلا عنوان",
    "Summary": "الملخص",
    "Skills — order": "المهارات — الترتيب",
    "Projects — order": "المشاريع — الترتيب",

    # --- ATS and formatting checks --------------------------------------------
    "Resume has no machine-readable text": "السيرة الذاتية لا تحتوي على نص قابل للقراءة آليًا",
    "Export the resume directly to PDF from your editor rather than scanning or exporting as an image.":
        "صدّر السيرة الذاتية مباشرة إلى PDF من المحرر بدلًا من مسحها ضوئيًا أو تصديرها كصورة.",
    "Most ATS will read this as blank.": "ستقرؤها معظم أنظمة التوظيف كصفحة فارغة.",
    "Multi-column layout": "تخطيط متعدد الأعمدة",
    "Move to a single-column layout.": "انتقل إلى تخطيط بعمود واحد.",
    "Many parsers read across columns and interleave the two, scrambling your job titles and dates.":
        "كثير من أنظمة القراءة تقرأ عبر الأعمدة وتخلط بينها، فتتداخل مسمياتك الوظيفية وتواريخك.",
    "Content laid out in tables": "محتوى منسّق داخل جداول",
    "Replace tables with plain paragraphs or bullets; cell content is often dropped.":
        "استبدل الجداول بفقرات أو نقاط عادية؛ فمحتوى الخلايا يُسقَط كثيرًا.",
    "Text sits in the page header or footer": "يوجد نص في رأس الصفحة أو تذييلها",
    "Move this into the body of the page.": "انقل هذا إلى متن الصفحة.",
    "If your contact details are up there, an ATS may discard them entirely.":
        "إذا كانت بيانات التواصل هناك، فقد يتجاهلها نظام التوظيف تمامًا.",
    "No email address found": "لم يُعثر على بريد إلكتروني",
    "No address matching an email pattern in the extracted text.":
        "لا يوجد في النص المستخرج عنوان يطابق نمط البريد الإلكتروني.",
    "Add a plain-text email in the body, not inside an image or header.":
        "أضف بريدًا إلكترونيًا نصيًا في متن الصفحة، لا داخل صورة أو في رأسها.",
    "No phone number found": "لم يُعثر على رقم هاتف",
    "No phone-shaped string in the extracted text.": "لا يوجد في النص المستخرج ما يشبه رقم هاتف.",
    "Add a contact number in the body of the resume.": "أضف رقم تواصل في متن السيرة الذاتية.",
    "Fonts are not embedded": "الخطوط غير مضمَّنة",
    "Re-export with fonts embedded, or switch to a standard face, so text extracts reliably.":
        "أعد التصدير مع تضمين الخطوط، أو استخدم خطًا قياسيًا، ليُستخرج النص بشكل موثوق.",
    "Trim to at most 2-3 pages, keeping the most recent and most relevant roles.":
        "اختصرها إلى صفحتين أو ثلاث على الأكثر، مع الإبقاء على الأدوار الأحدث والأكثر صلة.",
    "Use conventional headings (Experience, Education, Skills).":
        "استخدم عناوين مألوفة (الخبرة، التعليم، المهارات — أو Experience وEducation وSkills).",
    "Parsers key off these to file your content into the right fields.":
        "تعتمد أنظمة القراءة عليها لتصنيف محتواك في الحقول الصحيحة.",
    "Unconventional section headings": "عناوين أقسام غير مألوفة",
    "Rename to the conventional equivalent so a parser knows what the section is.":
        "غيّر اسمها إلى المقابل المألوف ليعرف نظام القراءة ماهية القسم.",
    "Phone number missing the +966 country code": "رقم الهاتف بلا رمز الدولة ‎+966",
    "Found a local-format Saudi mobile (05X) with no international prefix.":
        "وُجد رقم جوال سعودي بصيغة محلية (05X) دون البادئة الدولية.",
    "Write it as +966 5X XXX XXXX so recruiters outside the Kingdom can dial it.":
        "اكتبه بصيغة ‎+966 5X XXX XXXX‎ ليتمكن مسؤولو التوظيف خارج المملكة من الاتصال به.",
    "Re-export the resume as a text PDF and run the audit again.":
        "أعد تصدير السيرة الذاتية كملف PDF نصي ثم أعد الفحص.",
    "This file has no machine-readable text, so neither an applicant tracking system nor this audit can read it.":
        "هذا الملف لا يحتوي على نص قابل للقراءة آليًا، فلا يستطيع نظام التوظيف ولا هذا الفحص قراءته.",
    "Re-export it as a text PDF -- straight from your editor rather than as a scan or image -- and run it again.":
        "أعد تصديره كملف PDF نصي — مباشرة من المحرر لا كمسح ضوئي أو صورة — ثم أعد الفحص.",

    # --- keyword and experience deductions ------------------------------------
    "Not found anywhere in the resume.": "غير موجود في أي مكان من السيرة الذاتية.",
    "The job description lists this as critical.": "يذكر الوصف الوظيفي هذا كمتطلب أساسي.",
    "The job description lists this as preferred.": "يذكر الوصف الوظيفي هذا كمتطلب مفضَّل.",
    "If you have this experience, add it explicitly with the same wording the posting uses.":
        "إن كانت لديك هذه الخبرة، فأضفها صراحةً بنفس صياغة الإعلان.",
    "If you don't, treat it as a genuine gap to close rather than something to add.":
        "وإن لم تكن لديك، فتعامل معها كفجوة حقيقية تسدّها لا كشيء تضيفه.",
    "Make it explicit and quantify it, using the posting's wording.":
        "اجعلها صريحة وادعمها بالأرقام، مستخدمًا صياغة الإعلان.",
    "Based on titles and scope in the resume.": "بناءً على المسميات ونطاق العمل في السيرة الذاتية.",
    "You read as more senior than the posting.": "تبدو أعلى مستوى مما يطلبه الإعلان.",
    "Frame your experience toward the scope of this role so you don't screen out as overqualified.":
        "قدّم خبرتك بما يناسب نطاق هذا الدور حتى لا تُستبعد لكونك مؤهلًا أكثر من اللازم.",
    "You read as less senior than the posting asks.": "تبدو أقل مستوى مما يطلبه الإعلان.",
    "Lead with your largest-scope work and make ownership explicit.":
        "ابدأ بأوسع أعمالك نطاقًا ووضّح مسؤوليتك عنها صراحةً.",
    "There is a substantial seniority gap.": "هناك فجوة كبيرة في المستوى الوظيفي.",
    "Worth applying only with a strong referral, or targeting the level below.":
        "لا يستحق التقديم إلا بتوصية قوية، أو استهدف المستوى الأدنى.",
    "Check for relevant experience you haven't counted -- internships, freelance, or in-role project work often go unlisted.":
        "ابحث عن خبرة ذات صلة لم تحسبها — فالتدريب والعمل الحر ومشاريع العمل كثيرًا ما لا تُذكر.",
    "Address directly in your cover letter rather than leaving it unexplained.":
        "تناولها مباشرة في خطاب التقديم بدلًا من تركها دون تفسير.",

    # --- the CV review's own checks --------------------------------------------
    "No professional summary section": "لا يوجد قسم للملخص المهني",
    "No work experience section": "لا يوجد قسم للخبرة العملية",
    "No education section": "لا يوجد قسم للتعليم",
    "No skills section": "لا يوجد قسم للمهارات",
    "Nothing in the CV reads as a professional summary section.":
        "لا شيء في السيرة الذاتية يبدو قسمًا للملخص المهني.",
    "Nothing in the CV reads as a work experience section.":
        "لا شيء في السيرة الذاتية يبدو قسمًا للخبرة العملية.",
    "Nothing in the CV reads as a education section.":
        "لا شيء في السيرة الذاتية يبدو قسمًا للتعليم.",
    "Nothing in the CV reads as a skills section.":
        "لا شيء في السيرة الذاتية يبدو قسمًا للمهارات.",
    "Open with two or three lines on what you do, at what level, and what you are best at.":
        "ابدأ بسطرين أو ثلاثة عمّا تعمله، وبأي مستوى، وما تتميز فيه.",
    "It is the first thing a recruiter reads.": "إنه أول ما يقرؤه مسؤول التوظيف.",
    "Add your roles -- internships, part-time and volunteer work count -- each with a title, employer, dates and what you did.":
        "أضف أدوارك — ويُحتسب التدريب والعمل الجزئي والتطوعي — لكلٍّ منها مسمى وجهة عمل وتواريخ وما قمت به.",
    "Add your highest qualification with the institution and the year.":
        "أضف أعلى مؤهل لديك مع اسم الجهة والسنة.",
    "Many screens filter on it.": "كثير من عمليات الفرز تعتمد عليه.",
    "Add a short skills section naming the tools and methods you actually use.":
        "أضف قسمًا قصيرًا للمهارات يذكر الأدوات والأساليب التي تستخدمها فعلًا.",
    "An ATS matches keywords against it.": "يطابق نظام التوظيف الكلمات المفتاحية معه.",
    "Recruiters skim for results.": "يبحث مسؤولو التوظيف سريعًا عن النتائج.",
    "Where you know the figure -- people served, time saved, money, volume, team size -- add it.":
        "حيث تعرف الرقم — عدد من خدمتهم، أو الوقت الموفَّر، أو المال، أو الحجم، أو حجم الفريق — أضفه.",
    "Where you do not, leave it out rather than guess.": "وحيث لا تعرفه، فاتركه بدلًا من التخمين.",
    "Add two to four bullet points under each role: what you did, and what changed because of it.":
        "أضف من نقطتين إلى أربع تحت كل دور: ما الذي فعلته، وما الذي تغيّر بفضله.",
    "Add a start and end date to each role, month and year.":
        "أضف تاريخ بداية ونهاية لكل دور، بالشهر والسنة.",
    "Recruiters and ATS use them to count your years of experience.":
        "يستخدمها مسؤولو التوظيف وأنظمة التوظيف لحساب سنوات خبرتك.",
    "No LinkedIn or portfolio link": "لا يوجد رابط LinkedIn أو معرض أعمال",
    "The contact details list no web links.": "لا تتضمن بيانات التواصل أي روابط.",
    "Add your LinkedIn profile URL, and a portfolio or GitHub link if your work is public.":
        "أضف رابط ملفك على LinkedIn، ورابط معرض أعمال أو GitHub إن كانت أعمالك منشورة.",
    "Recruiters look before they call.": "يطّلع مسؤولو التوظيف عليها قبل الاتصال.",
    "No email address": "لا يوجد بريد إلكتروني",
    "The contact details have no email address.": "لا تتضمن بيانات التواصل بريدًا إلكترونيًا.",
    "Add a professional email address at the top of the CV.":
        "أضف بريدًا إلكترونيًا مهنيًا في أعلى السيرة الذاتية.",
    "No phone number": "لا يوجد رقم هاتف",
    "The contact details have no phone number.": "لا تتضمن بيانات التواصل رقم هاتف.",
    "Add a mobile number with the country code, such as +966 5X XXX XXXX.":
        "أضف رقم جوال مع رمز الدولة، مثل ‎+966 5X XXX XXXX‎.",

    # --- fields ----------------------------------------------------------------
    "The CV gives no evidence either way for this field's core skills.":
        "لا تقدّم السيرة الذاتية دليلًا في أي اتجاه على المهارات الأساسية لهذا المجال.",
    "The dates in the CV do not evidence time spent in this field.":
        "لا تُثبت التواريخ في السيرة الذاتية وقتًا قضيته في هذا المجال.",
    "Job titles in the CV are titles from this field.":
        "المسميات الوظيفية في السيرة الذاتية من هذا المجال.",
    "Titles are from a neighbouring discipline that transfers.":
        "المسميات من تخصص مجاور قابل للانتقال.",
    "Moving into this field would be a career change.":
        "الانتقال إلى هذا المجال سيكون تغييرًا في المسار المهني.",

    # --- job search --------------------------------------------------------------
    "No requirements clearly evidenced in your CV.": "لا توجد متطلبات مُثبتة بوضوح في سيرتك الذاتية.",
    "You read as more senior than this role.": "تبدو أعلى مستوى من هذا الدور.",
    "Reads a level above where your CV sits.": "الدور أعلى بمستوى مما تعكسه سيرتك الذاتية.",
    "Substantial seniority gap.": "فجوة كبيرة في المستوى الوظيفي.",
    "Google for Jobs was not searched: there is no JSEARCH_API_KEY in backend/.env.":
        "لم يتم البحث في Google للوظائف: لا يوجد JSEARCH_API_KEY في backend/.env.",
    "Type a role to search for something else.": "اكتب دورًا للبحث عن شيء آخر.",

    # --- employer targeting ---------------------------------------------------------
    "Read from this job posting only -- there is no research on the company behind it.":
        "مستخلص من هذا الإعلان الوظيفي فقط — دون أي بحث عن الشركة التي تقف وراءه.",
    "Points marked inferred are a reading of the posting, not facts about the employer.":
        "النقاط الموسومة بـ«مستنتَج» قراءة للإعلان، وليست حقائق عن جهة العمل.",

    # --- tailoring ---------------------------------------------------------------------
    "The suggested text is empty.": "النص المقترح فارغ.",
    "That is not a skill name.": "هذا ليس اسم مهارة.",
    "It is already in your skills list.": "إنها موجودة بالفعل في قائمة مهاراتك.",
    "No quote from your CV was given to show this skill, so it cannot be added.":
        "لم يُقدَّم اقتباس من سيرتك الذاتية يُثبت هذه المهارة، لذا لا يمكن إضافتها.",
    "Another suggestion already changes this.": "هناك اقتراح آخر يغيّر هذا بالفعل.",
    "That points at a part of the CV that does not exist.": "هذا يشير إلى جزء غير موجود في السيرة الذاتية.",
    "That points at a list that does not exist.": "هذا يشير إلى قائمة غير موجودة.",
    "The new order is not a rearrangement of the existing items — it drops, repeats or invents one.":
        "الترتيب الجديد ليس إعادة ترتيب للعناصر الموجودة — فهو يحذف عنصرًا أو يكرره أو يختلقه.",
    "Use [add number] and fill in the real one.": "استخدم [add number] وضع الرقم الحقيقي.",
    "It does appear elsewhere in your CV, but not here, so putting it here would attach it to the wrong place.":
        "إنه موجود في مكان آخر من سيرتك الذاتية لكن ليس هنا، ووضعه هنا ينسبه إلى المكان الخطأ.",
    "It is not in your CV at all.": "ليس موجودًا في سيرتك الذاتية إطلاقًا.",
    "That makes it a gap, not an edit.": "وهذا يجعله فجوة لا تعديلًا.",
    "Tailoring can only reword what is already there.": "التخصيص يعيد صياغة الموجود فقط.",
    "Fill in the figure instead.": "املأ الرقم بدلًا من ذلك.",
    "A figure cannot be empty.": "لا يمكن أن يكون الرقم فارغًا.",
    "Drop the edit instead if you do not have one.": "احذف التعديل بدلًا من ذلك إن لم يكن لديك رقم.",
    "A figure cannot contain square brackets.": "لا يمكن أن يحتوي الرقم على أقواس مربعة.",
    "It needs at least one digit.": "يجب أن يحتوي على خانة رقمية واحدة على الأقل.",

    # --- errors: reading a CV ----------------------------------------------------------------
    "There is no text to read.": "لا يوجد نص للقراءة.",
    "If this was a PDF, it has no text layer -- re-export it from your editor rather than as a scan.":
        "إن كان هذا ملف PDF، فهو بلا طبقة نصية — أعد تصديره من المحرر لا كمسح ضوئي.",
    "That document does not read as a CV.": "هذا المستند لا يبدو سيرة ذاتية.",
    "Upload a resume rather than a cover letter, transcript or job description.":
        "ارفع سيرة ذاتية بدلًا من خطاب تقديم أو كشف درجات أو وصف وظيفي.",
    "Resume must be under 15 MB.": "يجب أن يكون حجم السيرة الذاتية أقل من 15 ميغابايت.",
    "Resume not found.": "لم يُعثر على السيرة الذاتية.",
    "That CV's file is no longer on this server. Upload it again.":
        "لم يعد ملف هذه السيرة الذاتية موجودًا على الخادم. ارفعه من جديد.",
    "Upload it first.": "ارفعها أولًا.",
    "Analysis not found.": "لم يُعثر على التحليل.",
    "Version not found.": "لم يُعثر على النسخة.",
    "That file has no machine-readable text, so there is nothing to read.":
        "هذا الملف لا يحتوي على نص قابل للقراءة آليًا، فلا يوجد ما يُقرأ.",
    "Re-export it as a text PDF rather than a scan, or paste the text instead.":
        "أعد تصديره كملف PDF نصي لا كمسح ضوئي، أو الصق النص بدلًا من ذلك.",
    "That is too short to be a CV.": "هذا أقصر من أن يكون سيرة ذاتية.",
    "Paste the whole document.": "الصق المستند كاملًا.",
    "That resume has no machine-readable text, so it cannot be matched against anything.":
        "هذه السيرة الذاتية لا تحتوي على نص قابل للقراءة آليًا، فلا يمكن مطابقتها بأي شيء.",
    "Re-export it as a text PDF.": "أعد تصديرها كملف PDF نصي.",

    # --- errors: job descriptions and pages ---------------------------------------------------
    "Paste the full job description -- a short snippet can't be matched meaningfully.":
        "الصق الوصف الوظيفي كاملًا — فالمقتطف القصير لا تمكن مطابقته بشكل مفيد.",
    "Paste the full job description -- a snippet does not say enough.":
        "الصق الوصف الوظيفي كاملًا — فالمقتطف لا يقول ما يكفي.",
    "Paste the job description into the box below instead.":
        "الصق الوصف الوظيفي في المربع أدناه بدلًا من ذلك.",
    "That page had too little text to be a full job posting.":
        "نص هذه الصفحة أقل من أن يكون إعلانًا وظيفيًا كاملًا.",
    "That page could not be read.": "تعذّرت قراءة هذه الصفحة.",
    "That page could not be opened in time.": "تعذّر فتح هذه الصفحة في الوقت المتاح.",
    "It may be slow, or it may block automated readers.":
        "قد تكون بطيئة، أو قد تمنع القراءة الآلية.",
    "That site does not allow automated reading of its pages.":
        "هذا الموقع لا يسمح بالقراءة الآلية لصفحاته.",
    "Open the posting, copy its description, and paste it below.":
        "افتح الإعلان وانسخ وصفه ثم الصقه أدناه.",
    "That page publishes no structured job data, and browser fallback is off.":
        "هذه الصفحة لا تنشر بيانات وظيفية منظّمة، والقراءة عبر المتصفح متوقفة.",
    "That page publishes no structured job data, so reading it needs the model.":
        "هذه الصفحة لا تنشر بيانات وظيفية منظّمة، لذا تتطلب قراءتها نموذج الذكاء الاصطناعي.",
    "Add GEMINI_API_KEY to backend/.env and restart the server, or paste the job description instead.":
        "أضف GEMINI_API_KEY إلى backend/.env وأعد تشغيل الخادم، أو الصق الوصف الوظيفي بدلًا من ذلك.",
    "That page does not look like a single job posting.": "هذه الصفحة لا تبدو إعلانًا وظيفيًا واحدًا.",
    "Paste the link to one specific role rather than a search or listing page.":
        "الصق رابط دور محدد بدلًا من صفحة بحث أو قائمة وظائف.",
    "That page is behind a login wall or bot check, so it cannot be read automatically.":
        "هذه الصفحة خلف جدار تسجيل دخول أو فحص للروبوتات، فلا يمكن قراءتها آليًا.",
    "Open it yourself and paste the description into the Match tab instead.":
        "افتحها بنفسك والصق الوصف في تبويب المطابقة بدلًا من ذلك.",
    "A link to one specific role usually works; a search or listing page will not.":
        "رابط دور محدد يعمل عادةً؛ أما صفحة البحث أو قائمة الوظائف فلا.",
    "That link redirected somewhere on a private network, which this app will not follow.":
        "أعاد هذا الرابط التوجيه إلى شبكة خاصة، ولن يتبعه هذا التطبيق.",
    "This site's robots.txt forbids automated access to it.": "ملف robots.txt لهذا الموقع يمنع الوصول الآلي إليه.",
    "Paste a public job URL.": "الصق رابط وظيفة عامًا.",

    # --- errors: search, tailoring, versions ------------------------------------------------------
    "No Gemini API key.": "لا يوجد مفتاح Gemini API.",
    "Add GEMINI_API_KEY to backend/.env and restart the server.":
        "أضف GEMINI_API_KEY إلى backend/.env وأعد تشغيل الخادم.",
    "Pick at least one job to score.": "اختر وظيفة واحدة على الأقل للتقييم.",
    "Run a search first — those results have expired.": "ابحث أولًا — انتهت صلاحية تلك النتائج.",
    "None of those jobs are in the last search.": "لا توجد أي من تلك الوظائف في آخر بحث.",
    "That search result has expired.": "انتهت صلاحية نتيجة البحث هذه.",
    "Run the search again, then tailor.": "أعد البحث ثم خصّص.",
    "Run the search again.": "أعد البحث.",
    "Say which job to tailor for.": "حدّد الوظيفة التي تريد التخصيص لها.",
    "There is not enough of the job description to tailor against.":
        "الوصف الوظيفي غير كافٍ للتخصيص على أساسه.",
    "Paste the full posting, including its requirements.": "الصق الإعلان كاملًا بما فيه المتطلبات.",
    "That set of suggestions no longer exists.": "مجموعة الاقتراحات هذه لم تعد موجودة.",
    "This version failed a final check against your original CV and was not saved.":
        "لم تجتز هذه النسخة الفحص الأخير مقارنةً بسيرتك الذاتية الأصلية ولم تُحفظ.",
    "Nothing was changed.": "لم يتغير شيء.",
    "The original is the CV itself.": "النسخة الأصلية هي السيرة الذاتية نفسها.",
    "To remove it, delete the CV — that removes every version with it.":
        "لحذفها، احذف السيرة الذاتية — وسيحذف ذلك جميع النسخ معها.",
    "Too many requests.": "طلبات كثيرة جدًا.",

    # --- errors: the model and the job sources ------------------------------------------------------
    "Get one at https://aistudio.google.com/apikey, set GEMINI_API_KEY in backend/.env and restart the server.":
        "احصل على مفتاح من https://aistudio.google.com/apikey، وضعه في GEMINI_API_KEY داخل backend/.env، ثم أعد تشغيل الخادم.",
    "Gemini returned no reply.": "لم يُرسل Gemini أي رد.",
    "Gemini ran out of room before finishing its reply.": "نفدت المساحة المتاحة لـGemini قبل أن يُكمل رده.",
    "Try a shorter document.": "جرّب مستندًا أقصر.",
    "Gemini returned an empty reply.": "أرسل Gemini ردًا فارغًا.",
    "Could not reach the Gemini API.": "تعذّر الوصول إلى Gemini API.",
    "Check your connection.": "تحقّق من اتصالك.",
    "Check GEMINI_API_KEY in backend/.env and restart the server.":
        "تحقّق من GEMINI_API_KEY في backend/.env وأعد تشغيل الخادم.",
    "Gemini's rate limit or quota was reached.": "تم بلوغ حد الطلبات أو الحصة في Gemini.",
    "Try again shortly.": "حاول مرة أخرى بعد قليل.",
    "Gemini is overloaded right now.": "خدمة Gemini مزدحمة حاليًا.",
    "Try again in a minute.": "حاول مرة أخرى بعد دقيقة.",
    "No Gemini API key for the vision fallback.": "لا يوجد مفتاح Gemini API لقراءة لقطات الشاشة.",
    "Set GEMINI_API_KEY in backend/.env.": "ضع GEMINI_API_KEY في backend/.env.",
    "No JSearch API key.": "لا يوجد مفتاح JSearch API.",
    "Get a free one (200 requests/month) at https://www.openwebninja.com/api/jsearch and set JSEARCH_API_KEY.":
        "احصل على مفتاح مجاني (200 طلب شهريًا) من https://www.openwebninja.com/api/jsearch وضعه في JSEARCH_API_KEY.",
    "JSearch rejected the API key.": "رفض JSearch مفتاح API.",
    "Check JSEARCH_API_KEY in backend/.env.": "تحقّق من JSEARCH_API_KEY في backend/.env.",
    "JSearch sent back a response that could not be read.": "أرسل JSearch ردًا تعذّرت قراءته.",
    "It resets monthly.": "تتجدد الحصة شهريًا.",
}

# (English template, Arabic template). Tried in order, whole-string only, so a
# more specific template must come before a more general one that would also
# match it -- "Matched: {x} +{n} more." before "Matched: {x}.".
PATTERNS: list[tuple[str, str]] = [
    # --- checks and deductions ---------------------------------------------------
    ("Only {c} extractable characters across {p} page(s); pages are images.",
     "لا يوجد سوى {c} حرفًا قابلًا للاستخراج في {p} صفحة؛ الصفحات عبارة عن صور."),
    ("Only {c} extractable characters across {p} page(s).",
     "لا يوجد سوى {c} حرفًا قابلًا للاستخراج في {p} صفحة."),
    ("Side-by-side text columns detected on page(s) {pages}.",
     "رُصدت أعمدة نص متجاورة في الصفحة (الصفحات) {pages}."),
    ("Table structures on page(s) {pages}.", "هياكل جداول في الصفحة (الصفحات) {pages}."),
    ('Found in the header/footer band: "{sample}"', 'وُجد في شريط الرأس/التذييل: "{sample}"'),
    ("Non-embedded: {fonts}", "غير مضمَّنة: {fonts}"),
    ("Missing: {skill}", "مفقود: {skill}"),
    ("Weakly evidenced: {skill}", "دليل ضعيف: {skill}"),
    ('Closest evidence: "{quote}"', 'أقرب دليل: "{quote}"'),
    ("Seniority: resume reads {cv_level}, posting asks {jd_level}",
     "المستوى: السيرة الذاتية توحي بـ«{cv_level}»، والإعلان يطلب «{jd_level}»"),
    ("{n} years short of the stated requirement", "أقل من المتطلب المذكور بـ{n} سنة"),
    ("Resume evidences ~{cv} years; posting asks {jd}.",
     "تُثبت السيرة الذاتية نحو {cv} سنة، ويطلب الإعلان {jd}."),
    ("Experience gap: {gap}", "فجوة في الخبرة: {gap}"),
    ("Document is {n} pages.", "المستند من {n} صفحات."),
    ("{n} pages", "{n} صفحات"),
    ("No clear section heading for: {names}", "لا يوجد عنوان قسم واضح لـ: {names}"),
    ("Headings found: {found}", "العناوين الموجودة: {found}"),
    ("Styled as headings but not recognised: {sample}", "منسّقة كعناوين لكنها غير معروفة: {sample}"),
    ("{t_label} could not be assessed", "تعذّر تقييم «{t_label}»"),
    ("Only {n} of {total} bullet points include a number", "{n} فقط من أصل {total} نقاط تتضمن رقمًا"),
    ("{n} roles with no description", "{n} أدوار بلا وصف"),
    ("{n} role with no description", "{n} دور بلا وصف"),
    ("{n} roles with no dates", "{n} أدوار بلا تواريخ"),
    ("{n} role with no dates", "{n} دور بلا تواريخ"),

    # --- fields -----------------------------------------------------------------
    ("Evidences {n} of {total} core skills for this field.",
     "تُثبت {n} من أصل {total} من المهارات الأساسية لهذا المجال."),
    ("{n} year(s) evidenced, out of {full} for full marks.",
     "{n} سنة مُثبتة، من أصل {full} للحصول على الدرجة الكاملة."),

    # --- job search ----------------------------------------------------------------
    ("Matched: {skills} +{n} more.", "مطابق: {skills} و{n} أخرى."),
    ("Matched: {skills}.", "مطابق: {skills}."),
    ("Missing required: {skills} +{n}.", "متطلبات أساسية مفقودة: {skills} و{n} أخرى."),
    ("Missing required: {skills}.", "متطلبات أساسية مفقودة: {skills}."),
    ("Asks {jd} yrs, your CV evidences {cv}.", "يطلب {jd} سنوات، وتُثبت سيرتك الذاتية {cv}."),
    ("Google for Jobs: {t_problem}", "Google للوظائف: {t_problem}"),
    ("Google for Jobs found no roles on LinkedIn for “{query}”.",
     "لم يجد Google للوظائف أي أدوار على LinkedIn لـ«{query}»."),
    ("Google for Jobs found no roles for “{query}”.", "لم يجد Google للوظائف أي أدوار لـ«{query}»."),
    ("Google for Jobs could not be searched: {t_reason}", "تعذّر البحث في Google للوظائف: {t_reason}"),
    ("Google for Jobs was searched for “{query}”, the most recent title on your CV.",
     "تم البحث في Google للوظائف عن «{query}»، وهو أحدث مسمى وظيفي في سيرتك الذاتية."),
    ("JSearch returned an error ({code}).", "أعاد JSearch خطأ ({code})."),

    # --- tailoring ---------------------------------------------------------------------
    ("{t_who} — bullet order", "{t_who} — ترتيب النقاط"),
    ("{t_who} — bullet {n}", "{t_who} — النقطة {n}"),
    ("Project “{name}” — description", "المشروع «{name}» — الوصف"),
    ("Project {n} — description", "المشروع {n} — الوصف"),
    ("Skills — add “{skill}”", "المهارات — إضافة «{skill}»"),
    ("Adds the figure {figure}, which {t_where} does not contain.",
     "يضيف الرقم {figure}، وهو غير موجود في {t_where}."),
    ("Adds “{token}”, which {t_where} does not mention.", "يضيف «{token}»، وهو غير مذكور في {t_where}."),
    ("Brings in “{token}” from the job description; {t_where} does not mention it.",
     "يجلب «{token}» من الوصف الوظيفي، ولا يرد ذكره في {t_where}."),
    ("“{token}” claims a leadership role that {t_where} does not describe.",
     "«{token}» يدّعي دورًا قياديًا لا يرد في {t_where}."),
    ("“{token}” does not appear in {t_where}.", "«{token}» لا يرد في {t_where}."),
    ("At {n} characters it is too long for this part of a CV.",
     "بطول {n} حرفًا، إنه أطول من اللازم لهذا الجزء من السيرة الذاتية."),
    ("“{target}” is not a part of the CV that this kind of edit can change.",
     "«{target}» ليس جزءًا من السيرة الذاتية يمكن لهذا النوع من التعديل تغييره."),
    ("{ids} is not among the suggestions that can be accepted.",
     "{ids} ليس ضمن الاقتراحات التي يمكن قبولها."),
    ("{ids} are not among the suggestions that can be accepted.",
     "{ids} ليست ضمن الاقتراحات التي يمكن قبولها."),
    ("The original wording of “{t_label}” is not on record, so it cannot be restored.",
     "الصياغة الأصلية لـ«{t_label}» غير محفوظة، لذا لا يمكن استعادتها."),
    ("Those suggestions were withheld because they would have added something your CV does not say ({ids}), so they cannot be accepted.",
     "حُجبت هذه الاقتراحات لأنها كانت ستضيف شيئًا لا تقوله سيرتك الذاتية ({ids})، لذا لا يمكن قبولها."),
    ("This version still has {n} placeholder to fill in or drop before it can be exported.",
     "لا يزال في هذه النسخة {n} خانة يجب ملؤها أو حذفها قبل التصدير."),
    ("This version still has {n} placeholders to fill in or drop before it can be exported.",
     "لا يزال في هذه النسخة {n} خانات يجب ملؤها أو حذفها قبل التصدير."),
    ("Could not produce the {fmt} file: {error}", "تعذّر إنشاء ملف {fmt}: {error}"),
    ("“{value}…” is too long for a figure.", "«{value}…» أطول من أن يكون رقمًا."),
    ("“{value}” is not a figure.", "«{value}» ليس رقمًا."),
    ("There is no placeholder {ids} in this version.", "لا توجد خانة {ids} في هذه النسخة."),
    ("Too many redirects from {url}.", "إعادة توجيه كثيرة جدًا من {url}."),

    # --- errors ---------------------------------------------------------------------------
    ("Upload a PDF or DOCX (got {kind}).", "ارفع ملف PDF أو DOCX (الملف المستلم: {kind})."),
    ("{t_what} failed: {error}", "فشل {t_what}: {error}"),
    ("Could not read that page: {t_reason}", "تعذّرت قراءة تلك الصفحة: {t_reason}"),
    ("Not a usable URL: {url}", "رابط غير صالح: {url}"),
    ("Only http(s) URLs may be fetched: {url}", "لا يمكن جلب سوى روابط http(s):‏ {url}"),
    ("{host} is not on the allowlist.", "{host} ليس ضمن القائمة المسموح بها."),
    ("{url} matches a hard-blocked path.", "{url} يطابق مسارًا محظورًا."),
    ("robots.txt disallows {url}", "ملف robots.txt يمنع {url}"),
    ("{host} is a local or internal name.", "{host} اسم محلي أو داخلي."),
    ("{host} is a private or reserved address.", "{host} عنوان خاص أو محجوز."),
    ("{host} does not resolve: {error}", "تعذّر الوصول إلى {host}: {error}"),
    ("Try again in {n}s.", "حاول مرة أخرى بعد {n} ثانية."),
    ("Gemini did not return a valid {schema} after {n} attempts: {error}",
     "لم يُرجع Gemini نتيجة صالحة ({schema}) بعد {n} محاولات: {error}"),
    ("Gemini withheld its reply ({reason}).", "حجب Gemini رده ({reason})."),
    ("Gemini blocked this request ({reason}). {detail}", "حظر Gemini هذا الطلب ({reason}). {detail}"),
    ("Gemini blocked this request ({reason}).", "حظر Gemini هذا الطلب ({reason})."),
    # Google's own message sits inside this one, so it is matched whole before
    # the sentence splitter can cut it at Google's full stops.
    ("Gemini rejected the API key ({google}). Check GEMINI_API_KEY in backend/.env and restart the server.",
     "رفض Gemini مفتاح API ‏({google}). تحقّق من GEMINI_API_KEY في backend/.env وأعد تشغيل الخادم."),
    ("The Gemini API returned an error ({code}).", "أعاد Gemini API خطأ ({code})."),
]

# Only inside another message: a label within a label, the "where" of a
# provenance finding, the subject of "… failed". On their own they are too
# general -- "{a} at {b}" would rewrite a quoted bullet.
NESTED_PATTERNS: list[tuple[str, str]] = [
    ("your role at {company}", "دورك في {company}"),
    ("the project “{name}”", "المشروع «{name}»"),
    ("Role {n}", "الدور {n}"),
    ("{title} at {company}", "{title} في {company}"),
]

NESTED_EXACT: dict[str, str] = {
    "your CV": "سيرتك الذاتية",
    "this role": "هذا الدور",
    "this project": "هذا المشروع",
    "the quoted line": "السطر المقتبس",
    "the request did not go through.": "لم يكتمل الطلب.",
    "the JSearch quota is used up (the free plan allows 200 searches a month).":
        "نفدت حصة JSearch (تسمح الخطة المجانية بـ200 عملية بحث شهريًا).",
    # The subjects of "{what} failed", as `str.capitalize` leaves them.
    "Analysis": "التحليل",
    "Profile extraction": "قراءة السيرة الذاتية",
    "Field matching": "مطابقة المجالات",
    "Company targeting": "تحليل جهة العمل",
    "Tailoring": "التخصيص",
    "Cv review": "مراجعة السيرة الذاتية",
    "Core skills": "المهارات الأساسية",
    "ATS parseability": "قابلية القراءة في أنظمة التوظيف",
    "Keyword & skill match": "تطابق الكلمات المفتاحية والمهارات",
    "Experience & seniority fit": "ملاءمة الخبرة والمستوى الوظيفي",
    "Formatting & structure": "التنسيق والبنية",
}
