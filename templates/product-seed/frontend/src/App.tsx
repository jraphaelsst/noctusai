import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { Layout } from "@/components/layout/Layout";
import { Login } from "@/pages/Login";
import { Dashboard } from "@/pages/Dashboard";
import { SSOCallback } from "@noctusai/shared/components/SSOCallback";
import { PageSkeleton } from "@noctusai/shared/design-system";
import { supabase } from "@/integrations/supabase/client";

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isInitialized } = useAuthStore();

  if (!isInitialized) {
    return <PageSkeleton />;
  }

  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/sso"
        element={
          <SSOCallback
            coreUrl={CORE_URL}
            supabaseClient={supabase}
            onSessionReady={() => window.location.replace("/")}
          />
        }
      />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Layout>
              <Routes>
                <Route index element={<Dashboard />} />
                {/* Add your product routes here */}
              </Routes>
            </Layout>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}
