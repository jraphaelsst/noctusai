/**
 * kb-search — Supabase Edge Function
 *
 * Accepts a query string (and/or a precomputed embedding), calls the
 * `knowledge_extractor.match_kb` RPC, and returns ranked chunks as JSON.
 *
 * Request (POST, JSON):
 *   {
 *     "query"?:     string,           // natural-language query (embedded here)
 *     "embedding"?: number[],         // precomputed 1536-dim vector (skips OpenAI call)
 *     "k"?:         number            // max results, default 5
 *   }
 *
 * Either "query" or "embedding" must be present.
 *
 * Response (200, JSON):
 *   {
 *     "hits": [
 *       {
 *         "id":          string,
 *         "document_id": string,
 *         "content":     string,
 *         "module":      string,
 *         "confidence":  number,
 *         "similarity":  number   // cosine similarity in [0, 1]
 *       },
 *       ...
 *     ]
 *   }
 *
 * Environment variables (set in Supabase dashboard → Project Settings → Functions):
 *   SUPABASE_URL              — injected automatically by the runtime
 *   SUPABASE_SERVICE_ROLE_KEY — injected automatically by the runtime
 *   OPENAI_API_KEY            — required when "query" is used (not "embedding")
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RequestBody {
  query?: string;
  embedding?: number[];
  k?: number;
}

interface KBHit {
  id: string;
  document_id: string;
  content: string;
  module: string;
  confidence: number;
  similarity: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Call the OpenAI Embeddings API to generate a 1536-dim vector for `text`.
 * Uses text-embedding-3-small to match the ingest pipeline.
 */
async function embedQuery(text: string): Promise<number[]> {
  const apiKey = Deno.env.get("OPENAI_API_KEY");
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY is not set in the function environment.");
  }

  const resp = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "text-embedding-3-small",
      input: text,
    }),
  });

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`OpenAI embeddings error ${resp.status}: ${body}`);
  }

  const data = await resp.json();
  return data.data[0].embedding as number[];
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

Deno.serve(async (req: Request): Promise<Response> => {
  // CORS preflight — required for browser clients.
  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
      },
    });
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" },
    });
  }

  let body: RequestBody;
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON body" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const { query, embedding: precomputed, k = 5 } = body;

  if (!query && !precomputed) {
    return new Response(
      JSON.stringify({ error: 'Either "query" or "embedding" must be provided.' }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }

  // Resolve the query embedding.
  let queryEmbedding: number[];
  try {
    queryEmbedding = precomputed ?? (await embedQuery(query!));
  } catch (err) {
    return new Response(
      JSON.stringify({ error: `Embedding error: ${(err as Error).message}` }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  // Call the match_kb RPC via the Supabase client.
  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const supabase = createClient(supabaseUrl, serviceRoleKey);

  const { data, error } = await supabase
    .schema("knowledge_extractor")
    .rpc("match_kb", {
      query_embedding: queryEmbedding,
      match_count: k,
    });

  if (error) {
    return new Response(
      JSON.stringify({ error: `RPC error: ${error.message}` }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }

  const hits: KBHit[] = (data ?? []).map((row: Record<string, unknown>) => ({
    id: row.id as string,
    document_id: row.document_id as string,
    content: row.content as string,
    module: row.module as string,
    confidence: Number(row.confidence),
    similarity: Number(row.similarity),
  }));

  return new Response(JSON.stringify({ hits }), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
});
