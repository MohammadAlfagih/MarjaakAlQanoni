// Small inline icons (no icon library needed).
const base = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };

export const MicIcon = (p) => (
  <svg {...base} {...p}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
);
export const SendIcon = (p) => (
  <svg {...base} {...p}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
export const StopIcon = (p) => (
  <svg {...base} {...p}><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none" /></svg>
);
export const XIcon = (p) => (
  <svg {...base} {...p}><path d="M6 6l12 12M18 6L6 18" /></svg>
);
export const SpeakerIcon = (p) => (
  <svg {...base} width={16} height={16} {...p}><path d="M11 5L6 9H3v6h3l5 4V5zM15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" /></svg>
);
export const ScaleIcon = (p) => (
  <svg {...base} {...p}><path d="M12 4v16M5 7h14M7 7l-3 7a3.5 3.5 0 0 0 6 0zM17 7l-3 7a3.5 3.5 0 0 0 6 0zM8 20h8" /></svg>
);
export const BuildingIcon = (p) => (
  <svg {...base} {...p}><path d="M4 21V5l8-2v18M12 21V9l8 3v9M8 8v.01M8 12v.01M8 16v.01M16 15v.01M16 18v.01M3 21h18" /></svg>
);
export const AlertIcon = (p) => (
  <svg {...base} {...p}><path d="M12 3l9.5 17H2.5zM12 10v4M12 17v.01" /></svg>
);
export const QuestionIcon = (p) => (
  <svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.5V14M12 17v.01" /></svg>
);
export const BlockIcon = (p) => (
  <svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="M6 6l12 12" /></svg>
);
export const UploadIcon = (p) => (
  <svg {...base} width={32} height={32} {...p}><path d="M12 16V4M7 9l5-5 5 5M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></svg>
);
export const TrashIcon = (p) => (
  <svg {...base} width={18} height={18} {...p}><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></svg>
);
export const UserIcon = (p) => (
  <svg {...base} width={18} height={18} {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>
);
export const BriefcaseIcon = (p) => (
  <svg {...base} width={18} height={18} {...p}><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18" /></svg>
);
export const PlusIcon = (p) => (
  <svg {...base} width={16} height={16} {...p}><path d="M12 5v14M5 12h14" /></svg>
);
