/**
 * ImobShotAI -- video placeholder (`/imobshotai/video/novo`, status_pagina `imobshotai-video-novo`, initial status
 * `desenvolvimento`, contract §8). Video is blocked in v1; this page only says so.
 */
import { Link } from "react-router-dom";
import { Clapperboard } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function VideoNovo() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <h1 className="text-2xl font-semibold tracking-tight">Vídeo</h1>
      <Card data-testid="imobshotai-video-em-breve">
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <Clapperboard className="h-10 w-10 text-muted-foreground" />
          <p className="font-medium">Vídeo em breve</p>
          <p className="text-sm text-muted-foreground">
            A criação de vídeos a partir das fotos aprovadas ainda não está disponível no ImobShotAI.
          </p>
          <Button asChild variant="outline">
            <Link to="/imobshotai">Voltar ao quadro</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
