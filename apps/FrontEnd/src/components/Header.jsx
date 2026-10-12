import { Link, NavLink, useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext";
import { isMock } from "../api/client";

export default function Header() {
  const { t, toggleLang, session, logout } = useApp();
  const navigate = useNavigate();

  return (
    <header className="header">
      <Link to="/" className="brand">
        <img src="/favicon.svg" alt="" />
        <span>{t.appName}</span>
      </Link>

      {session && (
        <nav className="nav">
          <NavLink to="/chat">{t.navChat}</NavLink>
          {session.role === "hr" && session.company_id && <NavLink to="/policies">{t.navPolicies}</NavLink>}
        </nav>
      )}

      <div className="header-end">
        {isMock && <span className="mock-badge">{t.mockBadge}</span>}
        {session && (
          <div className="who">
            <strong>{session.name || (session.role === "hr" ? t.roleHr : t.roleEmployee)}</strong>
            {session.company_name || t.lawOnly}
          </div>
        )}
        <button className="btn btn-ghost" onClick={toggleLang}>{t.switchLang}</button>
        {session && (
          <button className="btn btn-ghost" onClick={() => { logout(); navigate("/"); }}>
            {t.logout}
          </button>
        )}
      </div>
    </header>
  );
}
