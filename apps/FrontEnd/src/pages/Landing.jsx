import { useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext";
import AnswerCard from "../components/AnswerCard";
import { AlertIcon, BuildingIcon, MicIcon, ScaleIcon } from "../components/Icons";

// A real sample answer is the hero: it shows what the product does.
const sample = {
  ar: {
    q: "كم يوم إجازتي السنوية؟",
    a: {
      id: "demo", status: "answered", conflict: false, lang: "ar",
      answer: "تستحق إجازة سنوية مدفوعة لا تقل عن 21 يوم، وتزيد إلى 30 يوم إذا أكملت 5 سنوات عند نفس صاحب العمل.",
      articles: [{ ref: "المادة 109", source: "law", quote: "يستحق العامل عن كل عام إجازة لا تقل مدتها عن واحد وعشرين يوماً…" }],
      next_steps: ["راجع رصيد إجازاتك مع الموارد البشرية", "قدّم طلب الإجازة كتابياً"],
    },
  },
  en: {
    q: "How many days of annual leave do I get?",
    a: {
      id: "demo", status: "answered", conflict: false, lang: "en",
      answer: "You are entitled to at least 21 days of paid annual leave, rising to 30 days after 5 years with the same employer.",
      articles: [{ ref: "Article 109", source: "law", quote: "The worker is entitled to annual leave of no less than 21 days…" }],
      next_steps: ["Check your leave balance with HR", "Submit your leave request in writing"],
    },
  },
};

export default function Landing() {
  const { t, lang, session } = useApp();
  const navigate = useNavigate();
  const s = sample[lang];

  const features = [
    { icon: <ScaleIcon />, title: t.feat1Title, text: t.feat1Text },
    { icon: <BuildingIcon />, title: t.feat2Title, text: t.feat2Text },
    { icon: <AlertIcon />, title: t.feat3Title, text: t.feat3Text },
    { icon: <MicIcon />, title: t.feat4Title, text: t.feat4Text },
  ];

  return (
    <main className="landing">
      <section className="hero">
        <div className="hero-copy">
          <h1>{t.heroTitle}</h1>
          <p>{t.heroText}</p>
          <div className="hero-actions">
            <button className="btn btn-lg" onClick={() => navigate(session ? "/chat" : "/login")}>
              {t.start}
            </button>
          </div>
        </div>

        <div className="demo" aria-hidden="true">
          <div className="msg-user"><div className="bubble-user">{s.q}</div></div>
          <AnswerCard msg={s.a} canSpeak={false} />
        </div>
      </section>

      <section className="features">
        {features.map((f) => (
          <div key={f.title}>
            {f.icon}
            <h3>{f.title}</h3>
            <p>{f.text}</p>
          </div>
        ))}
      </section>

      <p className="disclaimer">{t.disclaimer}</p>
    </main>
  );
}
