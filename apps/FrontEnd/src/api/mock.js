// ─────────────────────────────────────────────────────────────
// FAKE backend for building the UI before apps/api is ready.
// Answers are canned samples picked by keywords; article numbers and
// texts here are placeholders for the demo — the real answers come from
// the RAG backend.
// ─────────────────────────────────────────────────────────────

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const companies = [
  { id: "c_101", name: "شركة النخبة للتقنية" },
  { id: "c_102", name: "مجموعة الأفق التجارية" },
  { id: "c_103", name: "مصنع الريادة" },
];

export async function getCompanies() {
  await wait(250);
  return companies;
}

// ── Chat ─────────────────────────────────────────────────────

const has = (q, words) => words.some((w) => q.includes(w));

function respond(q, role, lang, history) {
  const ar = lang === "ar";
  const lastBot = [...history].reverse().find((m) => m.role === "assistant");

  // The user is replying to our "clarify" question about the contract
  if (lastBot?.status === "clarify") {
    return {
      status: "answered",
      conflict: true,
      answer: ar
        ? "شكراً للتوضيح. حتى لو الشرط مذكور في العقد أو فيه تعويض، النظام يبطل أي شرط ينقص حق العامل عن الحد النظامي، إلا إذا كان الشرط أفضل للعامل. فإذا التعويض أقل من قيمة الأيام الناقصة، الشرط غالباً غير نظامي."
        : "Thanks for clarifying. Even if the condition is in the contract or comes with compensation, the law voids any condition that reduces a worker's right below the legal minimum, unless it is better for the worker. If the compensation is worth less than the missing days, the condition is likely not compliant.",
      articles: [
        { ref: ar ? "المادة 8" : "Article 8", source: "law",
          quote: ar ? "يبطل كل شرط يخالف أحكام هذا النظام… ما لم يكن الشرط أكثر فائدة للعامل." : "Any condition contrary to this law is void… unless it is more beneficial to the worker." },
      ],
      next_steps: role === "hr"
        ? (ar ? ["راجع بند الإجازات في العقد وسياسة الشركة", "عدّل السياسة لتكون 21 يوم على الأقل", "عوّض الموظفين المتأثرين عن الأيام الناقصة"]
              : ["Review the leave clause in the contract and policy", "Update the policy to at least 21 days", "Compensate affected employees for the missing days"])
        : (ar ? ["احتفظ بنسخة من عقدك وسياسة الشركة", "تواصل مع الموارد البشرية كتابياً وطالب بحقك", "إذا ما انحلت، تقدّم بشكوى عبر القنوات الرسمية لوزارة الموارد البشرية"]
              : ["Keep a copy of your contract and the company policy", "Contact HR in writing and request your right", "If unresolved, file a complaint through the HRSD official channels"]),
    };
  }

  // Out of scope
  if (has(q, ["تأشيرة", "فيزا", "visa", "طقس", "weather", "مباراة", "football"])) {
    return {
      status: "out_of_scope",
      conflict: false,
      answer: ar
        ? "هذا السؤال خارج نطاقي. أقدر أساعدك بس في أسئلة نظام العمل السعودي وسياسات شركتك."
        : "This question is outside my scope. I can only help with Saudi Labor Law and your company's policies.",
      articles: [],
      next_steps: [],
    };
  }

  // Policy conflict: 15 days leave
  if (has(q, ["15", "١٥", "خمسة عشر", "fifteen"])) {
    if (role === "hr") {
      return {
        status: "answered",
        conflict: true,
        answer: ar
          ? "لا، الحد الأدنى للإجازة السنوية في النظام 21 يوم، وتصير 30 يوم إذا أكمل الموظف 5 سنوات. سياسة 15 يوم تخالف النظام."
          : "No. The legal minimum for annual leave is 21 days, rising to 30 days after 5 years of service. A 15-day policy conflicts with the law.",
        articles: [
          { ref: ar ? "المادة 109" : "Article 109", source: "law",
            quote: ar ? "يستحق العامل عن كل عام إجازة لا تقل مدتها عن واحد وعشرين يوماً…" : "The worker is entitled to annual leave of no less than twenty-one days…" },
          { ref: ar ? "سياسة الإجازات - بند 3" : "Leave policy - clause 3", source: "policy",
            quote: ar ? "يمنح الموظف 15 يوم إجازة سنوية مدفوعة." : "Employees receive 15 days of paid annual leave." },
        ],
        next_steps: ar
          ? ["عدّل سياسة الإجازات لتكون 21 يوم على الأقل", "راجع أرصدة إجازات الموظفين الحاليين", "المخاطرة: شكاوى عمالية وغرامات عند التفتيش"]
          : ["Update the leave policy to at least 21 days", "Review current employees' leave balances", "Risk: labor complaints and fines during inspection"],
      };
    }
    return {
      status: "clarify",
      conflict: true,
      answer: ar
        ? "سياسة شركتك تعطي 15 يوم، والنظام يعطي 21 يوم كحد أدنى. قبل ما أكمل: هل هذا مذكور في عقدك؟ وهل فيه تعويض مالي مقابل الأيام الناقصة؟"
        : "Your company policy gives 15 days, but the law sets a minimum of 21. Before I continue: is this stated in your contract? Is there financial compensation for the missing days?",
      articles: [
        { ref: ar ? "المادة 109" : "Article 109", source: "law",
          quote: ar ? "يستحق العامل عن كل عام إجازة لا تقل مدتها عن واحد وعشرين يوماً…" : "The worker is entitled to annual leave of no less than twenty-one days…" },
      ],
      next_steps: [],
    };
  }

  // Annual leave
  if (has(q, ["إجاز", "اجاز", "leave", "vacation"])) {
    return {
      status: "answered",
      conflict: false,
      answer: ar
        ? "تستحق إجازة سنوية مدفوعة لا تقل عن 21 يوم، وتزيد إلى 30 يوم إذا أكملت 5 سنوات متصلة عند نفس صاحب العمل."
        : "You are entitled to paid annual leave of at least 21 days, rising to 30 days after 5 consecutive years with the same employer.",
      articles: [
        { ref: ar ? "المادة 109" : "Article 109", source: "law",
          quote: ar ? "يستحق العامل عن كل عام إجازة لا تقل مدتها عن واحد وعشرين يوماً، تزاد إلى ثلاثين يوماً إذا أمضى خمس سنوات…" : "The worker is entitled to annual leave of no less than 21 days, increased to 30 days after five years…" },
      ],
      next_steps: role === "hr"
        ? (ar ? ["تأكد إن سياسة الإجازات تطابق هذا الحد", "حدّث الرصيد تلقائياً عند إكمال 5 سنوات"] : ["Make sure the leave policy matches this minimum", "Increase the balance automatically at 5 years"])
        : (ar ? ["راجع رصيد إجازاتك مع الموارد البشرية", "قدّم طلب الإجازة كتابياً قبل موعدها بوقت كافي"] : ["Check your leave balance with HR", "Submit your leave request in writing well in advance"]),
    };
  }

  // Late salary
  if (has(q, ["راتب", "رواتب", "متأخر", "salary", "late", "wage"]) && !has(q, ["خصم", "deduct"])) {
    return {
      status: "answered",
      conflict: false,
      answer: ar
        ? "يجب على صاحب العمل دفع الأجر في موعده المحدد. التأخير بدون سبب مشروع مخالفة، ويحق لك المطالبة بأجرك المتأخر."
        : "The employer must pay wages on time. A delay without a legitimate reason is a violation, and you have the right to claim your late wages.",
      articles: [
        { ref: ar ? "المادة 90" : "Article 90", source: "law",
          quote: ar ? "يجب دفع أجر العامل وكل مبلغ مستحق له بالعملة الرسمية للبلاد…" : "The worker's wage and all amounts due must be paid in the official currency…" },
      ],
      next_steps: role === "hr"
        ? (ar ? ["صرف الرواتب المتأخرة بأسرع وقت", "توضيح سبب التأخير للموظفين كتابياً", "المخاطرة: شكاوى عمالية وإيقاف خدمات المنشأة"] : ["Pay the late wages as soon as possible", "Explain the delay to employees in writing", "Risk: labor complaints and suspension of company services"])
        : (ar ? ["تواصل مع الموارد البشرية كتابياً (إيميل) واطلب موعد الصرف", "احتفظ بكشف حسابك وأي مراسلات", "إذا ما انحلت، تقدّم بشكوى عبر القنوات الرسمية لوزارة الموارد البشرية"] : ["Contact HR in writing (email) and ask for the payment date", "Keep your bank statements and any messages", "If unresolved, file a complaint through the HRSD official channels"]),
    };
  }

  // Deduction
  if (has(q, ["خصم", "يخصم", "deduct"])) {
    return {
      status: "answered",
      conflict: false,
      answer: ar
        ? "لا يجوز الخصم من أجر العامل إلا في حالات محددة في النظام، مثل استرداد القروض أو الغرامات النظامية، وبحدود معيّنة من الأجر."
        : "Deductions from wages are only allowed in specific cases set by the law, such as loan repayments or legal penalties, and within set limits.",
      articles: [
        { ref: ar ? "المادة 92" : "Article 92", source: "law",
          quote: ar ? "لا يجوز حسم أي مبلغ من أجور العامل لقاء حقوق خاصة دون موافقة كتابية منه، إلا في الحالات الآتية…" : "No amount may be deducted from a worker's wages for private claims without written consent, except in the following cases…" },
      ],
      next_steps: role === "hr"
        ? (ar ? ["تأكد إن الخصم من الحالات المسموحة", "وثّق سبب الخصم وأبلغ الموظف كتابياً", "رد على الموظف بالمادة وسبب الخصم"] : ["Confirm the deduction is an allowed case", "Document the reason and notify the employee in writing", "Reply to the employee citing the article and reason"])
        : (ar ? ["اطلب توضيح كتابي من الموارد البشرية عن سبب الخصم", "قارن السبب بالحالات المسموحة في المادة", "إذا الخصم غير نظامي، تقدّم بشكوى عبر القنوات الرسمية"] : ["Ask HR in writing for the reason", "Compare it with the allowed cases in the article", "If it's not allowed, file a complaint through official channels"]),
    };
  }

  // End of service
  if (has(q, ["نهاية الخدمة", "مكافأة", "end-of-service", "end of service", "gratuity"])) {
    return {
      status: "answered",
      conflict: false,
      answer: ar
        ? "مكافأة نهاية الخدمة: أجر نصف شهر عن كل سنة من السنوات الخمس الأولى، وأجر شهر عن كل سنة بعدها، على أساس آخر أجر."
        : "End-of-service pay: half a month's wage for each of the first five years, and a full month's wage for each year after, based on the last wage.",
      articles: [
        { ref: ar ? "المادة 84" : "Article 84", source: "law",
          quote: ar ? "إذا انتهت علاقة العمل وجب على صاحب العمل أن يدفع إلى العامل مكافأة عن مدة خدمته…" : "When the employment relationship ends, the employer must pay the worker an award for the period of service…" },
      ],
      next_steps: role === "hr"
        ? (ar ? ["احسب على آخر أجر شامل البدلات الثابتة", "انتبه لحالات الاستقالة لأنها تقلل المكافأة"] : ["Calculate on the last wage including fixed allowances", "Note that resignation reduces the award"])
        : (ar ? ["اطلب من الموارد البشرية كشف حساب المكافأة", "تأكد إن الحساب على آخر أجر لك"] : ["Ask HR for a breakdown of your award", "Make sure it uses your last wage"]),
    };
  }

  // Nothing relevant
  return {
    status: "unknown",
    conflict: false,
    answer: ar
      ? "ما لقيت مادة في النظام أو في سياسات شركتك تجاوب سؤالك بشكل موثّق. أنصحك تتواصل مع وزارة الموارد البشرية عبر قنواتها الرسمية."
      : "I couldn't find an article in the law or your company's policies that answers this reliably. Please contact HRSD through its official channels.",
    articles: [],
    next_steps: [],
  };
}

export async function sendQuestion({ question, role, lang, history }) {
  await wait(900);
  return { ...respond(question.toLowerCase(), role, lang, history), lang };
}

export async function sendVoice({ audio, role, lang, history }) {
  await wait(1400);
  // A real backend runs STT on `audio`. The mock pretends the user asked this:
  const transcript = lang === "ar" ? "راتبي متأخر شهرين، وش أسوي؟" : "My salary is two months late. What should I do?";
  return {
    ...respond(transcript.toLowerCase(), role, lang, history),
    lang,
    transcript,
    audio_url: null, // null → the UI reads the answer with the browser's voice
  };
}

// ── Policies (kept in memory, resets on reload) ─────────────

let nextId = 4;
const policies = {
  c_101: [
    { id: "p1", filename: "سياسة الإجازات.pdf", size: 245000, uploaded_at: "2026-10-01T09:12:00Z" },
    { id: "p2", filename: "لائحة تنظيم العمل الداخلية.docx", size: 512000, uploaded_at: "2026-09-20T11:40:00Z" },
  ],
  c_102: [{ id: "p3", filename: "Leave Policy 2026.pdf", size: 180000, uploaded_at: "2026-10-05T08:00:00Z" }],
  c_103: [],
};

export async function getPolicies(company_id) {
  await wait(300);
  return [...(policies[company_id] || [])];
}

export async function uploadPolicy(company_id, file) {
  await wait(1200);
  const item = { id: "p" + nextId++, filename: file.name, size: file.size, uploaded_at: new Date().toISOString() };
  (policies[company_id] ||= []).unshift(item);
  return item;
}

export async function deletePolicy(id) {
  await wait(300);
  for (const k of Object.keys(policies)) policies[k] = policies[k].filter((p) => p.id !== id);
  return null;
}
