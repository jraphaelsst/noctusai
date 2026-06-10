/**
 * MailchimpNotConnected — shown when GET /api/mailchimp/connection returns
 * { connected: false }. Links to the Configuração page.
 */
import { Mail, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function MailchimpNotConnected() {
  return (
    <div className="flex items-center justify-center min-h-[400px] p-6">
      <Card className="max-w-md w-full text-center" data-testid="mailchimp-not-connected">
        <CardHeader>
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-muted">
            <Mail className="h-7 w-7 text-muted-foreground" />
          </div>
          <CardTitle>Mailchimp não conectado</CardTitle>
          <CardDescription>
            Conecte sua conta Mailchimp para gerenciar contatos, listas,
            templates e campanhas de email.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild className="gap-2">
            <Link to="/email-marketing/configuracao">
              Conectar Mailchimp
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
