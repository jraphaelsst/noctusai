import { Routes, Route, useLocation } from "react-router-dom";
import { ROUTES } from "./lib/routes";
import { SiteLayout } from "./components/SiteLayout";
import { ConsentProvider } from "./lib/consent";
import { SettingsProvider } from "./lib/settings";
import { ThemeProvider } from "./lib/theme";
import Home from "./pages/Home";
import ProductsIndex from "./pages/ProductsIndex";
import ProductPage from "./pages/ProductPage";
import Solutions from "./pages/Solutions";
import Pricing from "./pages/Pricing";
import Contact from "./pages/Contact";
import Waitlist from "./pages/Waitlist";
import About from "./pages/About";
import NotFound from "./pages/NotFound";

function pageForRoute(id: string, product?: string) {
  if (id === "home") return <Home />;
  if (id === "products-index") return <ProductsIndex />;
  if (id.startsWith("product-") && product) return <ProductPage slug={product} />;
  if (id === "solutions") return <Solutions />;
  if (id === "pricing") return <Pricing />;
  if (id === "contact") return <Contact />;
  if (id === "waitlist") return <Waitlist />;
  if (id === "about") return <About />;
  return <NotFound />;
}

function RouteEntry({ id, product }: { id: string; product?: string }) {
  const location = useLocation();
  return <SiteLayout path={location.pathname}>{pageForRoute(id, product)}</SiteLayout>;
}

/**
 * The full route tree — shared verbatim by `entry-client.tsx` (BrowserRouter)
 * and `entry-server.tsx` (StaticRouter). Every `RouteDef` contributes TWO
 * `<Route>`s (pt + en), both rendering the same page component; the page
 * itself reads locale off the URL via `SiteLayout`/`LocaleProvider`, never
 * off two different component trees.
 */
export function AppRoutes() {
  return (
    <SettingsProvider>
      <ThemeProvider>
        <ConsentProvider>
          <Routes>
            {ROUTES.flatMap((r) => [
              <Route key={`${r.id}-pt`} path={r.pt} element={<RouteEntry id={r.id} product={r.product} />} />,
              <Route key={`${r.id}-en`} path={r.en} element={<RouteEntry id={r.id} product={r.product} />} />,
            ])}
            <Route path="*" element={<RouteEntry id="not-found" />} />
          </Routes>
        </ConsentProvider>
      </ThemeProvider>
    </SettingsProvider>
  );
}
