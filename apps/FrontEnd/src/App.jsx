import { Navigate, Route, Routes } from "react-router-dom";
import { useApp } from "./context/AppContext";
import Header from "./components/Header";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Chat from "./pages/Chat";
import Policies from "./pages/Policies";

// Policy management requires an HR session with a selected company.
function Guard({ children, hrOnly = false }) {
  const { session } = useApp();
  if (!session) return <Navigate to="/login" replace />;
  if (hrOnly && (session.role !== "hr" || !session.company_id)) return <Navigate to="/chat" replace />;
  return children;
}

export default function App() {
  return (
    <>
      <Header />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/chat" element={<Guard><Chat /></Guard>} />
        <Route path="/policies" element={<Guard hrOnly><Policies /></Guard>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
