import { useNavigate } from "react-router-dom";
import { Home, ArrowLeft } from "lucide-react";

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="min-h-[60vh] flex items-center justify-center px-4">
      <div className="text-center space-y-6 max-w-md">
        <h1 className="text-7xl font-bold text-primary">404</h1>
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold">Page not found</h2>
          <p className="text-muted-foreground">The page you are looking for does not exist.</p>
        </div>
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-muted"
          >
            <ArrowLeft className="h-4 w-4" /> Back
          </button>
          <button
            onClick={() => navigate("/")}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Home className="h-4 w-4" /> Home
          </button>
        </div>
      </div>
    </div>
  );
}
