import { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { ArrowLeftRight, LogOut, RefreshCw } from 'lucide-react';
import { ProductIcon } from '../../lib/product-icon';

interface Product {
  id: string;
  nome: string;
  slug: string;
  icone: string | null;
  logout_behavior: string;
  ativo: boolean;
}

export function AdminLogoutBehavior() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);

  async function fetchProducts() {
    setLoading(true);
    try {
      const res = await api.get('/api/products');
      setProducts(res.data || []);
    } catch {
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchProducts(); }, []);

  async function toggleBehavior(product: Product) {
    const newBehavior = product.logout_behavior === 'redirect' ? 'signout' : 'redirect';
    setToggling(product.id);
    try {
      await api.patch(`/api/products/${product.id}`, { logout_behavior: newBehavior });
      setProducts(prev =>
        prev.map(p => p.id === product.id ? { ...p, logout_behavior: newBehavior } : p)
      );
    } catch (err: any) {
      alert(err.message || 'Erro ao atualizar');
    } finally {
      setToggling(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-8">
        <h1 className="text-xl sm:text-2xl font-bold text-foreground">Comportamento de Logout</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Controle o que acontece quando usuarios clicam em "Sair" em cada produto.
        </p>
      </div>

      {/* Legend */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6 p-4 rounded-lg bg-muted/50 text-sm">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-primary" />
          <span className="text-muted-foreground">
            <strong className="text-foreground">Redirecionar</strong> — volta ao NoctusAI, SSO ativo
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-destructive" />
          <span className="text-muted-foreground">
            <strong className="text-foreground">Desconectar</strong> — encerra a sessao do usuario
          </span>
        </div>
      </div>

      {/* Product list */}
      <div className="space-y-3">
        {products.map(product => {
          const isRedirect = product.logout_behavior === 'redirect';
          const isToggling = toggling === product.id;

          return (
            <div
              key={product.id}
              className="flex items-center justify-between gap-4 rounded-lg border border-border bg-card p-4 sm:p-5 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="shrink-0"><ProductIcon name={product.icone || 'Box'} size="sm" /></span>
                <div className="min-w-0">
                  <p className="font-medium text-foreground truncate">{product.nome}</p>
                  <p className="text-xs text-muted-foreground">{product.slug}</p>
                </div>
              </div>

              <button
                onClick={() => toggleBehavior(product)}
                disabled={isToggling}
                className={`
                  shrink-0 flex items-center gap-2 rounded-full px-4 py-2 text-xs font-medium transition-all
                  disabled:opacity-50 disabled:cursor-not-allowed
                  ${isRedirect
                    ? 'bg-primary/10 text-primary hover:bg-primary/20'
                    : 'bg-destructive/10 text-destructive hover:bg-destructive/20'
                  }
                `}
              >
                {isToggling ? (
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                ) : isRedirect ? (
                  <ArrowLeftRight className="h-3.5 w-3.5" />
                ) : (
                  <LogOut className="h-3.5 w-3.5" />
                )}
                {isRedirect ? 'Redirecionar' : 'Desconectar'}
              </button>
            </div>
          );
        })}
      </div>

      {products.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          Nenhum produto cadastrado
        </div>
      )}
    </div>
  );
}
