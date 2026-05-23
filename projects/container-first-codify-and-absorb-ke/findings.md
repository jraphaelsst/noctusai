# findings — container-first codification + knowledge-extractor absorption

Append in-the-moment. Categories: slips · errors · mistakes · lessons · knowledge.

## knowledge
- **Canonical house-container shape** (the spec the keeper enforces) lives in `products/seed/backend/Dockerfile` + `products/seed/docker-compose.yml`: multi-stage `noctus-seed-frontend-base AS frontend-build` → `noctus-seed-backend-base AS runtime` → `runtime AS runtime-watch`; `SERVE_SPA_DIR`; `VITE_SAME_ORIGIN=1`; single-service compose `target: runtime-watch`, source bind-mounts + anon `node_modules` volumes, `noctus-net external:true`, mandatory profile-gated `<slug>-tunnel` w/ `--protocol http2`.
- **Two container shapes exist** (drift): seed-WORKSPACE scaffold = 2-Dockerfile workspace-root (`templates/seed-workspace-docker/`, per `new-product.md` §9-10); in-noc product = single-container house model. Absorb gate bridges them. Codification targets in-noc products.
- **knowledge-extractor** = standalone sibling repo (`../knowledge-extractor`, branch `methodology-dev`), a "noc product in waiting" (its CLAUDE.md mirrors noc seams 1:1 for absorption). Step-1 platform built + tested; has NO Docker artifacts yet. Persistence = Supabase schema `knowledge_extractor` (live DB authorized separately).

## lessons
- The P1 keeper + P3 containerize form a validation loop: post-absorption (P2) the keeper FLAGS knowledge-extractor as missing the house shape; P3 containerizes → keeper green = the methodology proven on the pilot.

## slips / errors / mistakes
- (none yet)
