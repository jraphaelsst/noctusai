import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-background">
      <div className="flex flex-col md:flex-row">
        <Sidebar />
        <div className="flex-1 min-w-0">
          <Header />
          <main className="p-4 sm:p-6">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}