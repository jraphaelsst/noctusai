"""Every notification Social Wiring sends — declared, so core's "Notificações" page lists it and the owner can
switch it off (`noctusai_lib.domain.notification_catalog`).

Adding a send = adding a kind HERE in the same change. `NotificationService._dispatch` refuses an undeclared kind.
Texts are pt-BR and shown verbatim to the owner: say what arrives and exactly what triggers it.
"""
from __future__ import annotations

from noctusai_lib.domain.notification_catalog import NotificationKind, declare_kinds

PRODUCT = "social-wiring"

KINDS: tuple[NotificationKind, ...] = (
    NotificationKind(
        kind="upload",
        titulo="Vídeo publicado",
        descricao="Aviso de que um vídeo agendado foi publicado, com o link, para quem foi marcado no envio.",
        gatilho="Um envio (upload_jobs) termina com status publicado e tem destinatários marcados.",
        canais=("whatsapp", "email"),
    ),
    NotificationKind(
        kind="lead",
        titulo="Novo lead de anúncio",
        descricao="Nome, telefone, formulário e campanha de um lead que acabou de chegar pelo Meta Ads.",
        gatilho="O webhook de leadgen do Meta grava um lead novo.",
        canais=("whatsapp", "email"),
    ),
    NotificationKind(
        kind="conflito",
        titulo="Conflito de campo em lead",
        descricao="Um dado do lead chegou diferente do que já estava salvo; a mensagem mostra o valor antigo e o novo.",
        gatilho="A sincronização de um lead encontra um campo divergente que não sobrescreve sozinha.",
        canais=("whatsapp", "email"),
    ),
    NotificationKind(
        kind="conflito_imovel",
        titulo="Conflito de campo em imóvel",
        descricao="Um dado do imóvel no Vista diverge do que está no Social Wiring; mostra os dois valores.",
        gatilho="A sincronização de imóveis com o Vista encontra um campo divergente.",
        canais=("whatsapp", "email"),
    ),
    NotificationKind(
        kind="conflito_empresa",
        titulo="Conflito de campo em empresa",
        descricao="Um dado de empresa diverge entre a origem e o que está salvo; mostra os dois valores.",
        gatilho="A sincronização de empresas encontra um campo divergente.",
        canais=("whatsapp", "email"),
    ),
    NotificationKind(
        kind="visita_feedback",
        titulo="Visita aconteceu?",
        descricao="Pergunta diária aos corretores do card (ou à lista da organização) se a visita marcada aconteceu.",
        gatilho="Rotina diária encontra roteiros com data de visita passada e sem resposta.",
        canais=("whatsapp", "email"),
    ),
    NotificationKind(
        kind="vista_divergencias",
        titulo="Divergências com o Vista",
        descricao="Resumo de campos de imóveis que divergem entre o Vista e o Social Wiring, com link para decidir. "
                  "Vai para o usuário destino configurado em Imóveis → Divergências.",
        gatilho="Uma sincronização de imóveis abre divergências novas (no máximo 4 resumos por hora).",
    ),
    NotificationKind(
        kind="imoveis_delistados",
        titulo="Imóveis saíram do Vista",
        descricao="Lista os códigos que a sincronização marcou como fora do Vista, destacando os exclusivos e os "
                  "imóveis PAUSADOS no site à espera da sua decisão (restaurar ou confirmar que saíram). Nada é apagado.",
        gatilho="Uma sincronização de imóveis termina tendo delistado ou pausado 1 ou mais imóveis nesta execução — "
                "uma mensagem por execução, só com códigos novos.",
    ),
    NotificationKind(
        kind="imoveis_novos_vista",
        titulo="Imóveis novos no Vista",
        descricao="Códigos que apareceram no Vista e foram criados do nosso lado (aviso informativo).",
        gatilho="Uma sincronização de imóveis encontra 1 ou mais códigos que não tínhamos — uma mensagem por execução.",
    ),
    NotificationKind(
        kind="imoveis_sync_falhou",
        titulo="Sincronização de imóveis falhou",
        descricao="A sincronização com o Vista terminou com erro ou incompleta; mostra o motivo resumido.",
        gatilho="Uma execução de imoveis_sync termina com status diferente de ok (exceto listar_vazio) e a execução anterior "
                "não tinha esse mesmo status — avisa na mudança, não a cada 2h.",
    ),
    NotificationKind(
        kind="imoveis_vista_listar_vazio",
        titulo="Vista não está listando imóveis",
        descricao="O Vista parou de responder à listagem; a atualização segue imóvel a imóvel e imóveis novos só "
                  "aparecem se a sonda de códigos os encontrar.",
        gatilho="Uma sincronização automática recebe a listagem vazia do Vista — no máximo 1 aviso a cada 24h.",
        canais=("whatsapp", "email", "in_app"),
    ),
    NotificationKind(
        kind="julia_alerta",
        titulo="Alerta da Julia",
        descricao="A Julia sinalizou algo na conversa: lead insatisfeito, erro dela, pedido fora do escopo ou outra "
                  "deriva. Vai para o destino de relatórios da Julia, com o link da conversa.",
        gatilho="O agente emite a ação 'alerta' durante um turno com um lead.",
        canais=("whatsapp", "in_app"),
    ),
    NotificationKind(
        kind="julia_opt_out",
        titulo="Lead pediu para parar de receber mensagens",
        descricao="Nome e telefone mascarados do lead, o motivo (as palavras do agente sobre por que o lead quis parar; se o "
                  "agente não deu, como foi detectado) e o trecho do pedido.",
        gatilho="O agente registra um opt-out do lead.",
        canais=("whatsapp", "in_app"),
    ),
    NotificationKind(
        kind="julia_handoff",
        titulo="Relatório de passagem para humano",
        descricao="Resumo do lead quando a Julia passa a conversa para a equipe.",
        gatilho="A Julia faz handoff de uma conversa.",
    ),
    NotificationKind(
        kind="julia_conclusao",
        titulo="Relatório de lead pronto",
        descricao="Resumo do lead (perfil, imóveis oferecidos, próximos passos) quando a Julia conclui a qualificação.",
        gatilho="O agente marca o lead como pronto (ação 'lead_pronto' com relatório).",
    ),
)

declare_kinds(PRODUCT, KINDS)
