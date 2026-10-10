/**
 * Media Creation — the media-PRODUCTION arm of the social-wiring product.
 *
 * Three tabs:
 *   - Biblioteca   : list of drafts / ready / published posts
 *   - Novo post    : compose → idea → 3-stage LLM generation pipeline
 *   - Branding     : brandings grouped by marca (tokens, brand book, components, assets)
 *
 * The three generation stages — storyboard, image prompts, copy — each
 * call the backend's POST /api/media-creation/posts/{id}/generate/* and
 * persist artifacts on the post. Rendering produces AI images when a Gemini
 * key is configured, else a visible brand-locked SVG placeholder. Every post
 * is built on the in-home Método Audience methodology (dominant trigger +
 * template + capa→identificacao→virada→nome→prova→valor→cta skeleton).
 */
import { useState } from "react";
import { Library, Palette, Plus, Wand2 } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { BrandingTab } from "@/components/branding/BrandingTab";
import { ComposeTab } from "@/components/geracao/carrosseis/ComposeTab";
import { LibraryTab } from "@/components/geracao/carrosseis/LibraryTab";

export default function MediaCreation() {
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"library" | "compose" | "brand">("library");

  return (
    <div className="space-y-6 p-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <Wand2 className="h-6 w-6 text-primary" />
            Criação de mídia
          </h1>
          <p className="text-sm text-muted-foreground">
            A camada de produção do ecossistema de automação. Brief → roteiro
            → prompts → legenda. Os prompts saem prontos para o GalilAI / Nano
            Banana / Midjourney.
          </p>
        </div>
      </header>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
        <TabsList>
          <TabsTrigger value="library" className="gap-2">
            <Library className="h-4 w-4" />
            Biblioteca
          </TabsTrigger>
          <TabsTrigger value="compose" className="gap-2">
            <Plus className="h-4 w-4" />
            Novo post
          </TabsTrigger>
          <TabsTrigger value="brand" className="gap-2">
            <Palette className="h-4 w-4" />
            Branding
          </TabsTrigger>
        </TabsList>

        <TabsContent value="library" className="mt-4">
          <LibraryTab
            selectedPostId={selectedPostId}
            onSelect={setSelectedPostId}
          />
        </TabsContent>

        <TabsContent value="compose" className="mt-4">
          <ComposeTab
            onCreated={(id) => {
              setSelectedPostId(id);
              setActiveTab("library");
            }}
          />
        </TabsContent>

        <TabsContent value="brand" className="mt-4">
          <BrandingTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
