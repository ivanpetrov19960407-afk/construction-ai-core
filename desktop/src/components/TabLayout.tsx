import { type ReactNode } from "react";

export interface TabItem {
  key: string;
  title: string;
  content: ReactNode;
}

interface TabLayoutProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (tabKey: string) => void;
}

export default function TabLayout({
  tabs,
  activeTab,
  onChange,
}: TabLayoutProps) {
  return (
    <section style={{ display: "grid", gap: 12 }}>
      <nav style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {tabs.map((tab) => {
          const isActive = tab.key === activeTab;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => onChange(tab.key)}
              style={{
                borderRadius: 10,
                border: "1px solid #cbd5e1",
                padding: "8px 12px",
                background: isActive ? "#2563eb" : "transparent",
                color: isActive ? "#fff" : "inherit",
                fontWeight: isActive ? 700 : 500,
              }}
            >
              {tab.title}
            </button>
          );
        })}
      </nav>
      <div>{tabs.find((tab) => tab.key === activeTab)?.content}</div>
    </section>
  );
}
