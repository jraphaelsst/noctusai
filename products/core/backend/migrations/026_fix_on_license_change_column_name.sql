-- ============================================================
-- 026 — Fix on_license_change trigger: products.name → products.nome
-- ============================================================
-- The on_license_change AFTER INSERT trigger (added 2026-04-09 in the
-- provisioning lifecycle work) referenced a non-existent products.name
-- column when composing the "Novo produto disponível" notification.
-- The actual column is `nome` (PT-BR — products table is fully PT-BR:
-- nome / descricao / icone / cor / ativo).
--
-- PL/pgSQL function bodies aren't validated at CREATE FUNCTION time —
-- they parse lazily on first execution — so the original migration
-- deployed clean and every license INSERT after 2026-04-09 raised
-- `[500] column "name" does not exist`. Surfaced 2026-05-05 when
-- granting media-scheduling access (first grant attempt since the bug
-- landed).
--
-- This migration redefines the function with the correct column name.
-- 001_noctusai_core.sql is also patched so fresh deploys are correct.
-- ============================================================

CREATE OR REPLACE FUNCTION public.on_license_change()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  v_slug text;
  v_org_id uuid;
BEGIN
  SELECT slug INTO v_slug FROM public.products WHERE id = NEW.product_id;
  v_org_id := NEW.org_id;
  IF TG_OP = 'INSERT' AND NEW.status = 'active' THEN
    CASE v_slug
      WHEN 'erp-imobiliario' THEN PERFORM public.provision_erp(v_org_id);
      WHEN 'personal-finance' THEN PERFORM public.provision_personal_finance(v_org_id);
      WHEN 'therapy-platform' THEN PERFORM public.provision_therapy(v_org_id);
      ELSE NULL;
    END CASE;
    INSERT INTO public.notifications (user_id, org_id, type, title, message, metadata)
    SELECT nu.id, v_org_id, 'system',
      'Novo produto disponível',
      'Sua organização agora tem acesso ao ' || COALESCE((SELECT nome FROM public.products WHERE id = NEW.product_id), v_slug) || '!',
      jsonb_build_object('product', v_slug, 'license_id', NEW.id, 'action', 'granted')
    FROM public.noctus_users nu WHERE nu.org_id = v_org_id;
  ELSIF TG_OP = 'UPDATE' AND OLD.status = 'active' AND NEW.status = 'revoked' THEN
    PERFORM public.deprovision_product(v_org_id, v_slug);
  END IF;
  RETURN NEW;
END;
$$;
