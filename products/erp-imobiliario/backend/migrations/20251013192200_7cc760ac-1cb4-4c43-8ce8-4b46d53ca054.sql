-- Deletar configurações antigas com tipo diaria (usaremos apenas mensais)
DELETE FROM metas_config 
WHERE tipo = 'diaria';