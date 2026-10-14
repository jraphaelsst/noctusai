/**
 * `/` -- the ERP dashboard (seed `ErpDashboard`): finance, stock, purchasing, contracts and quotes tiles, composed over
 * this product's organ hooks. A tile group renders only for an organ whose hooks are passed here.
 */
import { ErpDashboard } from "@noctusai/lib";
import { useNavigate } from "react-router-dom";

import {
  contractsHooks,
  financeHooks,
  inventoryHooks,
  quotesHooks,
  usePurchasingHooks,
} from "@/lib/erpHooks";

const ROUTES: Record<string, string> = {
  finance: "/financeiro",
  inventory: "/estoque",
  purchasing: "/compras",
  contracts: "/contratos",
  quotes: "/orcamentos",
};

export default function Dashboard() {
  const navigate = useNavigate();
  const purchasing = usePurchasingHooks();
  return (
    <ErpDashboard
      finance={financeHooks}
      inventory={inventoryHooks}
      purchasing={purchasing}
      contracts={contractsHooks}
      quotes={quotesHooks}
      onNavigate={(target) => ROUTES[target] && navigate(ROUTES[target])}
    />
  );
}
