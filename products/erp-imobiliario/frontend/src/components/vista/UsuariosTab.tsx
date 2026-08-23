/**
 * Vista showcase — Usuários tab. The internal Vista team roster.
 * Moved out of `pages/VistaShowcase.tsx` unchanged (2026-08-22 split).
 *
 * Doubles as the ungated substitute for the 401'd Corretores tab: brokers
 * appear here with `Setor: Corretores` (vista.md § 4.5).
 */
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useVistaUsuarios } from '@/hooks/useVistaShowcase';
import { EmptyPanel, ErrorPanel } from './shared';

export function UsuariosTab() {
  const { data: usuarios, isLoading, isError, error } = useVistaUsuarios(true);
  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (isError) return <ErrorPanel error={error as Error} />;
  if (!usuarios || usuarios.length === 0) {
    return <EmptyPanel message="Nenhum usuário interno retornado pela Vista." />;
  }
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Foto</TableHead>
              <TableHead>Nome</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Setor</TableHead>
              <TableHead>Código</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {usuarios.map(u => (
              <TableRow key={u.codigo}>
                <TableCell>
                  {u.foto_url
                    ? <img src={u.foto_url} alt={u.nome ?? u.codigo} className="h-8 w-8 rounded-full object-cover" loading="lazy" />
                    : <div className="h-8 w-8 rounded-full bg-slate-200" />}
                </TableCell>
                <TableCell className="font-medium">{u.nome ?? '—'}</TableCell>
                <TableCell>{u.email ?? '—'}</TableCell>
                <TableCell>{u.setor ?? '—'}</TableCell>
                <TableCell className="text-xs text-slate-500">{u.codigo}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
