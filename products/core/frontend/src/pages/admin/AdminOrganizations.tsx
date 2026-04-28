import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface Organization {
  id: string;
  nome: string;
  slug: string;
  plano: string;
  created_at: string;
}

export function AdminOrganizations() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    api.get('/api/organizations')
      .then(res => setOrgs(res.data || []))
      .catch(err => console.error('Error:', err))
      .finally(() => setLoading(false));
  }, []);

  const filtered = orgs.filter(o =>
    o.nome.toLowerCase().includes(search.toLowerCase()) ||
    o.slug?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        <p className="ml-3 text-muted-foreground">Carregando...</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Organizacoes</h1>
          <p className="text-muted-foreground mt-1">{orgs.length} organizacoes registradas</p>
        </div>
      </div>

      <div className="mb-4">
        <input
          type="text"
          placeholder="Buscar organizacao..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full max-w-md h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
        />
      </div>

      <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Nome</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Slug</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Plano</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Criado em</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filtered.map(org => (
              <tr key={org.id} className="hover:bg-muted/50 transition-colors">
                <td className="px-4 py-3 font-medium text-foreground">{org.nome}</td>
                <td className="px-4 py-3"><code className="text-sm bg-muted px-1.5 py-0.5 rounded">{org.slug}</code></td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center rounded-full px-2 py-1 text-xs font-medium bg-primary/10 text-primary">
                    {org.plano || 'free'}
                  </span>
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {org.created_at ? new Date(org.created_at).toLocaleDateString('pt-BR') : '\u2014'}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                  Nenhuma organizacao encontrada
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
