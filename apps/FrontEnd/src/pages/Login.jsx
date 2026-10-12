import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext";
import { getCompanies } from "../api/client";
import { BriefcaseIcon, UserIcon } from "../components/Icons";

// Demo login: no password. Picks a role and a company (company_id isolates policies).
export default function Login() {
  const { t, login } = useApp();
  const navigate = useNavigate();
  const [companies, setCompanies] = useState(null);
  const [error, setError] = useState("");
  const [role, setRole] = useState("employee");
  const [companyId, setCompanyId] = useState("");
  const [name, setName] = useState("");

  useEffect(() => {
    getCompanies().then(setCompanies).catch(() => setError(t.errorGeneric));
  }, [t.errorGeneric]);

  function submit(e) {
    e.preventDefault();
    const company = companies.find((c) => c.id === companyId);
    login({ role, company_id: company.id, company_name: company.name, name: name.trim() });
    navigate("/chat");
  }

  const roles = [
    { id: "employee", icon: <UserIcon />, title: t.roleEmployee, hint: t.roleEmployeeHint },
    { id: "hr", icon: <BriefcaseIcon />, title: t.roleHr, hint: t.roleHrHint },
  ];

  return (
    <main className="center-page">
      <form className="panel" onSubmit={submit}>
        <h1>{t.loginTitle}</h1>
        <p>{t.loginText}</p>

        <div className="field">
          <span className="field-label">{t.roleLabel}</span>
          <div className="roles">
            {roles.map((r) => (
              <button type="button" key={r.id} className="role" aria-pressed={role === r.id} onClick={() => setRole(r.id)}>
                <strong>{r.icon}{r.title}</strong>
                <span>{r.hint}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label htmlFor="company">{t.companyLabel}</label>
          <select id="company" className="select" value={companyId} onChange={(e) => setCompanyId(e.target.value)} disabled={!companies}>
            <option value="">{companies ? t.companyPlaceholder : t.loading}</option>
            {companies?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>

        <div className="field">
          <label htmlFor="name">{t.nameLabel}</label>
          <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} />
        </div>

        {error && <p className="error">{error}</p>}

        <button className="btn btn-lg" style={{ width: "100%" }} disabled={!companyId}>
          {t.continue}
        </button>
      </form>
    </main>
  );
}
