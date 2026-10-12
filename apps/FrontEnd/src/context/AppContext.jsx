import { createContext, useContext, useEffect, useState } from "react";
import { strings } from "../i18n/strings";

// Holds the UI language and the "session" (role + company).
// The session is kept in sessionStorage so a page refresh doesn't log you out.
const AppContext = createContext(null);

function load(key, fallback) {
  try {
    const v = sessionStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
}
function save(key, value) {
  try {
    if (value == null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage blocked, ignore */
  }
}

export function AppProvider({ children }) {
  const [lang, setLang] = useState(() => load("lang", "ar"));
  const [session, setSession] = useState(() => load("session", null));

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    document.title = strings[lang].appName;
    save("lang", lang);
  }, [lang]);

  useEffect(() => save("session", session), [session]);

  const value = {
    lang,
    t: strings[lang],
    toggleLang: () => setLang((l) => (l === "ar" ? "en" : "ar")),
    session, // { role: "employee" | "hr", company_id, company_name, name }
    login: (s) => setSession(s),
    logout: () => setSession(null),
  };
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export const useApp = () => useContext(AppContext);
