import { useState } from 'react';
import { Loader2, Receipt, Download } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { formatCurrency, formatDate } from '@/lib/utils';
import { useInvoices } from '@/hooks/useInvoices';

const STATUS_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  emitido: { label: 'Emitido', variant: 'default' },
  pendente: { label: 'Pendente', variant: 'outline' },
  cancelado: { label: 'Cancelado', variant: 'destructive' },
};

export default function PatientInvoices() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useInvoices(page);

  const invoices = data?.data ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 10);

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Receipt className="h-6 w-6" /> Meus Recibos
        </h1>
        <p className="text-muted-foreground">Recibos e comprovantes das suas sessoes</p>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : invoices.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Receipt className="h-10 w-10 text-muted-foreground/30" />
            <p className="mt-3 text-sm text-muted-foreground">Nenhum recibo encontrado</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="p-4 pb-2">Data</th>
                      <th className="p-4 pb-2">Descricao</th>
                      <th className="p-4 pb-2 text-right">Valor</th>
                      <th className="p-4 pb-2">Status</th>
                      <th className="p-4 pb-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.map((invoice) => {
                      const badge = STATUS_BADGE[invoice.status] ?? STATUS_BADGE.pendente;
                      return (
                        <tr key={invoice.id} className="border-b last:border-0">
                          <td className="p-4 whitespace-nowrap">{formatDate(invoice.created_at)}</td>
                          <td className="p-4">{invoice.descricao ?? 'Sessao de terapia'}</td>
                          <td className="p-4 text-right font-medium">{formatCurrency(invoice.valor)}</td>
                          <td className="p-4">
                            <Badge variant={badge.variant}>{badge.label}</Badge>
                          </td>
                          <td className="p-4">
                            {invoice.pdf_url && (
                              <Button size="sm" variant="ghost" asChild>
                                <a href={invoice.pdf_url} target="_blank" rel="noopener noreferrer">
                                  <Download className="h-4 w-4 mr-1" /> PDF
                                </a>
                              </Button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {totalPages > 1 && (
            <div className="flex justify-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</Button>
              <span className="text-sm text-muted-foreground flex items-center px-2">Pagina {page} de {totalPages}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Proxima</Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
