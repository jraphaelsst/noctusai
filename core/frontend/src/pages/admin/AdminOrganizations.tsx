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
    return <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>;
  }

  return (
    <div>
      <div className="admin-page-header">
        <div>
          <h1 className="admin-page-title">Organizações</h1>
          <p className="admin-page-subtitle">{orgs.length} organizações registradas</p>
        </div>
      </div>

      <div className="admin-toolbar">
        <input
          type="text"
          placeholder="Buscar organização..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="admin-search"
        />
      </div>

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Nome</th>
              <th>Slug</th>
              <th>Plano</th>
              <th>Criado em</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(org => (
              <tr key={org.id}>
                <td className="admin-table-primary">{org.nome}</td>
                <td><code>{org.slug}</code></td>
                <td><span className="badge">{org.plano || 'free'}</span></td>
                <td>{org.created_at ? new Date(org.created_at).toLocaleDateString('pt-BR') : '—'}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={4} className="admin-table-empty">Nenhuma organização encontrada</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
