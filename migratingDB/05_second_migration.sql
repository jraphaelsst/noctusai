-- =====================================================================
-- FASE 2: Migração Corretiva + Enriquecimento
-- Arquivo monolítico — executar em uma ÚNICA sessão SQL
--
-- Pré-requisito: Fase 1 concluída (migratingDB/01-04)
-- =====================================================================
--
-- O QUE ESTE SCRIPT FAZ:
-- ─────────────────────────────────────────────────────────────────────
-- ETAPA 1  │ Staging: recria tabelas temporárias e carrega dados
-- ETAPA 2  │ Mapeamentos corretos (tipo_imovel e zona com dados reais)
-- ETAPA 3  │ Corrige tipo_imovel nos ativos
-- ETAPA 4  │ Corrige zona nos ativos
-- ETAPA 5  │ Substitui "Corretor #N" por nomes reais
-- ETAPA 6  │ Corrige tipo_imovel e zona dentro do JSONB interesses
-- ETAPA 7  │ Enriquece erp.clientes com dados reais dos proprietários
-- ETAPA 8  │ Enriquece erp.condominios com dados reais
-- ETAPA 9  │ Popula localização dos imóveis a partir dos condominios
-- ETAPA 10 │ Validação
-- ─────────────────────────────────────────────────────────────────────

BEGIN;

-- ═════════════════════════════════════════════════════════════════════
-- ETAPA 1: Staging Tables + Data Loading
-- ═════════════════════════════════════════════════════════════════════

-- 1A. Tabelas originais (re-criadas para JOINs via ref)

CREATE TEMP TABLE stg_imovel (
  id INTEGER PRIMARY KEY,
  ref TEXT,
  valor_venda INTEGER,
  condominio_id INTEGER,
  criado_por_id INTEGER,
  proprietario_id INTEGER,
  tipo_id INTEGER,
  zona_id INTEGER,
  corretor_id INTEGER
);

CREATE TEMP TABLE stg_permuta_imovel (
  id INTEGER PRIMARY KEY,
  tipo_id INTEGER,
  condominio TEXT,
  zona_id INTEGER,
  cep TEXT,
  estado TEXT,
  cidade TEXT,
  bairro TEXT,
  endereco TEXT,
  valor INTEGER,
  criado_por_id INTEGER,
  proprietario_id INTEGER,
  codigo TEXT,
  numero TEXT,
  corretor_id INTEGER,
  ref TEXT
);

-- 1B. Tabelas de lookup (dados novos da secondMig/)

CREATE TEMP TABLE stg_tipo_imovel (id INTEGER PRIMARY KEY, nome TEXT NOT NULL);
CREATE TEMP TABLE stg_zona (id INTEGER PRIMARY KEY, nome TEXT NOT NULL);
CREATE TEMP TABLE stg_tipo_automovel (id INTEGER PRIMARY KEY, nome TEXT NOT NULL);
CREATE TEMP TABLE stg_corretor (id INTEGER PRIMARY KEY, nome TEXT, telefone TEXT, email TEXT);
CREATE TEMP TABLE stg_proprietario (id INTEGER PRIMARY KEY, nome TEXT, telefone TEXT, email TEXT, corretor_id INTEGER);
CREATE TEMP TABLE stg_condominio (id INTEGER PRIMARY KEY, nome TEXT, cep TEXT, estado TEXT, cidade TEXT, bairro TEXT, endereco TEXT, numero INTEGER, km INTEGER, valor_condominio NUMERIC);

-- ─────────────────────────────────────────────────────────────────────
-- 1C. Dados originais dos imóveis (264 registros)
-- ─────────────────────────────────────────────────────────────────────

INSERT INTO stg_imovel (id, ref, valor_venda, condominio_id, criado_por_id, proprietario_id, tipo_id, zona_id, corretor_id) VALUES
  (17, 'ONE8193', 2900000, 5, 4, 3, 7, 4, 3),
  (18, 'ONE9225', 1500000, 6, 4, 6, 3, 4, NULL),
  (19, 'ONE7320', 260000, 8, 4, 7, 8, NULL, 5),
  (20, 'ONE8200', 359000, 9, 4, 8, 3, 4, NULL),
  (21, 'ONE6448', 1500000, 10, 4, 9, 7, 4, 2),
  (22, 'ONE7791', 2150000, 11, 4, 10, 7, 4, 7),
  (23, 'ONE9423', 2200000, 13, 4, 11, 7, 4, NULL),
  (24, 'ONE6173', 1850000, 14, 4, 12, 7, 4, NULL),
  (25, 'ONE9296', 2930000, 15, 4, 13, 7, 4, 4),
  (26, 'ONE9109', 1156000, 16, 4, 14, 9, 4, NULL),
  (27, 'AP0576', 850000, 17, 4, 15, 1, NULL, 2),
  (30, 'ONE6919', 1598000, 20, 4, 17, 7, 4, NULL),
  (32, 'ONE9349', 380000, 21, 4, 18, 10, 4, NULL),
  (33, 'ONE9419', 880000, 22, 4, 20, 7, 4, 2),
  (34, 'ONE6270', 479000, 23, 4, 21, 1, 4, 2),
  (35, 'ONE9500', 250000, 24, 4, 22, 1, 6, NULL),
  (36, 'ONE5357', 1390000, 25, 4, 23, 7, 4, 2),
  (37, 'ONE6084', 570000, 26, 4, 11, 7, 4, 2),
  (38, 'ONE8970', 960000, 27, 4, 24, 7, 4, 2),
  (39, 'ONE7779', 1180000, 28, 4, 25, 7, 4, 2),
  (40, 'CA1564', 120000, 13, 4, 26, 7, 4, NULL),
  (41, 'ONE9227', 1350000, 29, 4, 27, 7, 4, NULL),
  (42, 'CA3776', 1600000, 30, 4, 28, 7, NULL, 3),
  (43, 'ONE6531', 2400000, 31, 4, 11, 7, 4, NULL),
  (44, 'ONE7314', 2150000, 32, 4, 29, 7, 4, 5),
  (45, 'ONE6162', 2190000, 33, 4, 30, 7, 4, 4),
  (46, 'ONE7312', 2320000, 34, 4, 31, 7, 4, 12),
  (47, 'ONE8661', 2690000, 13, 4, 11, 7, 4, NULL),
  (48, 'ONE6678', 2690000, 35, 4, 32, 7, 4, NULL),
  (49, 'ONE6104', 3000000, 30, 4, 33, 7, 4, NULL),
  (50, 'ONE8614', 2900000, 30, 4, 34, 7, 4, 5),
  (51, 'ONE9003', 3400000, 34, 4, 35, 7, 4, 4),
  (52, 'ONE7963', 4000000, 36, 4, 36, 7, 4, 5),
  (54, 'CA5002', 6980500, 35, 4, 38, 7, 4, 5),
  (55, 'ONE6109', 11000000, 30, 4, 39, 7, 4, 5),
  (56, 'PR0013', 15100000, 37, 4, 40, 11, 4, NULL),
  (57, 'ONE8685', 1150000, 38, 4, 40, 7, 4, NULL),
  (58, 'ONE8677', 1200000, 39, 4, 11, 7, 4, NULL),
  (59, 'ONE8696', 1270000, 40, 4, 40, 7, 4, NULL),
  (60, 'ONE8642', 2500000, 41, 4, 40, 7, 4, NULL),
  (61, 'ONE8540', 3200000, 13, 4, 40, 7, 4, NULL),
  (63, 'ONE6723', 192600, 42, 4, 41, 3, 4, 2),
  (64, 'ONE5581', 205000, 43, 4, 42, 10, 4, NULL),
  (65, 'ONE5565', 205000, 43, 4, 42, 10, 4, NULL),
  (66, 'TE0883', 280000, 44, 4, 43, 3, NULL, 2),
  (68, 'TE0280', 250000, 45, 4, 44, 3, 4, NULL),
  (70, 'ONE7041', 342400, 46, 4, 46, 1, 4, 2),
  (72, 'TE0576', 350000, 47, 4, 47, 3, 4, NULL),
  (75, 'CA5229', 420000, 48, 4, 49, 7, 4, 2),
  (77, 'TE0510', 420000, 11, 4, 50, 3, 4, 2),
  (79, 'ONE9445', 430000, 50, 4, 51, 2, 4, 13),
  (81, 'ONE9445', 430000, 50, 4, 51, 2, 4, 13),
  (82, 'AP0687', 445000, 51, 4, 52, 1, 4, 2),
  (83, 'ONE5619', 450000, 52, 4, 53, 1, 4, NULL),
  (84, 'ONE8113', 450000, 53, 4, 54, 9, 4, 13),
  (85, 'TE1025', 450000, 54, 4, 32, 3, 4, NULL),
  (86, 'ONE8402', 490990, 55, 4, 56, 3, NULL, NULL),
  (87, 'ONE9221', 530000, 34, 4, 11, 3, 4, NULL),
  (88, 'ONE6084', 570000, 26, 4, 11, 7, 4, 2),
  (91, 'ONE7030', 599000, 56, 4, 57, 7, 4, NULL),
  (93, 'ONE7699', 600000, 57, 4, 11, 3, 4, NULL),
  (94, 'ONE7516', 620000, 38, 4, 58, 3, 4, 1),
  (95, 'ONE8119', 550000, 58, 4, 59, 7, 4, NULL),
  (97, 'ONE9304', 750000, 59, 4, 60, 2, 4, NULL),
  (98, 'ONE6154', 752600, 60, 4, 61, 7, 4, NULL),
  (100, 'ONE5903', 837000, 57, 4, 11, 3, 4, NULL),
  (101, 'ONE6365', 850000, 61, 4, 62, 7, 4, 2),
  (102, 'ONE5479', 850000, 61, 4, 63, 7, 4, 2),
  (103, 'ONE7505', 850000, 62, 4, 64, 7, 4, 5),
  (105, 'ONE7200', 850000, 63, 4, 65, 3, 4, 2),
  (106, 'ONE6315', 945000, 64, 4, 68, 7, 4, 13),
  (107, 'TE1171', 890000, 65, 4, 40, 3, 4, NULL),
  (109, 'ONE9396', 1200000, 66, 4, 69, 7, 4, 13),
  (110, 'ONE9215', 960000, 13, 4, 70, 7, 4, 4),
  (111, 'TE1072', 1000000, 30, 4, 71, 3, 4, 3),
  (112, 'CA0190', 1000000, 67, 4, 72, 7, 4, 5),
  (115, 'CA2136', 1050000, 60, 4, 74, 7, 4, 4),
  (116, 'ONE7832', 1072000, 69, 4, 75, 7, 4, NULL),
  (117, 'CA2476', 1080000, 18, 4, 76, 7, 4, 4),
  (118, 'TE0672', 1850000, 70, 4, 77, 3, 4, NULL),
  (119, 'CA0680', 1400000, 71, 4, 78, 7, 4, 2),
  (120, 'ONE6108', 1150000, 31, 4, 79, 7, 4, NULL),
  (121, 'ONE7066', 1250000, 72, 4, 81, 7, 4, NULL),
  (122, 'AP0552', 1276000, 17, 4, 82, 1, 4, 2),
  (123, 'CA3654', 1280000, 31, 4, 83, 7, 4, 12),
  (124, 'ONE8457', 1300000, 71, 4, 84, 7, 4, 14),
  (126, 'ONE7491', 1280000, 73, 4, 85, 7, 4, 13),
  (127, 'CA4923', 1390000, 31, 4, 86, 7, 4, NULL),
  (128, 'ONE8807', 1400000, 74, 4, 27, 7, 4, NULL),
  (129, 'ONE5452', 1450000, 75, 4, 88, 7, 4, 2),
  (130, 'CA2090', 1450000, 76, 4, 89, 7, 4, 2),
  (131, 'ONE5599', 1490000, 30, 4, 11, 7, 4, NULL),
  (132, 'ONE8287', 1600000, 77, 4, 91, 2, NULL, 2),
  (133, 'ONE7973', 1600000, 78, 4, 11, 7, 4, NULL),
  (136, 'CA3036', 1600000, 20, 4, 92, 7, 4, 4),
  (137, 'CA2944', 1600000, 13, 4, 93, 7, 4, 4),
  (138, 'ONE6352', 1600000, 79, 4, 94, 7, 4, 13),
  (139, 'CA4710', 1648000, 80, 4, 95, 7, 4, NULL),
  (140, 'CA3593', 1650000, 81, 4, 96, 7, 4, 5),
  (142, 'ONE9117', 1650000, 82, 4, 97, 7, 4, 15),
  (143, 'ONE6506', 1698000, 83, 4, 98, 7, 4, 13),
  (144, 'CA3934', 1700000, 84, 4, 99, 7, 4, NULL),
  (145, 'AR0019', 2040000, 85, 4, 100, 14, 4, NULL),
  (146, 'ONE7831', 2350000, 86, 4, 101, 3, 4, 15),
  (147, 'ONE9200', 1800000, 87, 4, 102, 2, 4, 4),
  (148, 'CA4470', 1800000, 88, 4, 103, 7, NULL, 3),
  (149, 'ONE7786', 1800000, 14, 4, 104, 7, 4, 2),
  (150, 'CA4849', 1800000, 89, 4, 105, 7, 4, 5),
  (151, 'CA4187', 1800000, 90, 4, 106, 7, 4, NULL),
  (152, 'CA1720', 2000000, 71, 4, 107, 7, 4, 2),
  (153, 'ONE6649', 1880000, 76, 4, 108, 7, 4, 2),
  (154, 'ONE6993', 1750000, 38, 4, 109, 7, 4, 1),
  (156, 'ONE7397', 1950000, 30, 4, 110, 7, 4, 5),
  (157, 'ONE6512', 1950000, 91, 4, 40, 7, 4, 7),
  (158, 'ONE9239', 1750000, 92, 4, 111, 7, 4, NULL),
  (159, 'ONE8184', 1980000, 93, 4, 11, 7, 4, NULL),
  (160, 'TE1073', 2000000, 94, 4, 71, 3, 4, 3),
  (161, 'CA3797', 2000000, 30, 4, 113, 7, 4, 3),
  (162, 'CA4866', 2000000, 79, 4, 114, 7, 4, 2),
  (163, 'ONE7577', 1990000, 95, 4, 11, 7, 4, NULL),
  (164, 'ONE5613', 2100000, 96, 4, 115, 7, 4, 5),
  (165, 'ONE6286', 2148000, 31, 4, 116, 7, 4, 16),
  (166, 'AR0035', 2150000, 97, 4, 40, 14, 4, NULL),
  (167, 'ONE8167', 2200000, 98, 4, 117, 2, 4, 5),
  (168, 'ONE7696', 2200000, 30, 4, 11, 7, 4, NULL),
  (169, 'ONE6113', 2200000, 38, 4, 118, 7, 4, NULL),
  (170, 'ONE5578', 2200000, 99, 4, 119, 7, 4, 5),
  (171, 'CA4372', 2200000, 67, 4, 120, 7, 4, NULL),
  (172, 'CA3739', 2198000, 100, 4, 121, 7, 4, NULL),
  (173, 'CA1666', 2200000, 101, 4, 122, 7, 4, 14),
  (174, 'CA4815', 2230000, 102, 4, 123, 7, 4, NULL),
  (175, 'CA3832', 2300000, 38, 4, 124, 7, 4, NULL),
  (176, 'ONE7365', 2348000, 67, 4, 125, 7, 4, 14),
  (177, 'CA3150', 2350000, 103, 4, 126, 7, 4, 5),
  (178, 'ONE7379', 2375000, 104, 4, 11, 3, 4, NULL),
  (179, 'CA4998', 2380000, 67, 4, 128, 7, 4, NULL),
  (180, 'CA4461', 2400000, 30, 4, 129, 7, 4, NULL),
  (181, 'ONE8788', 2440000, 105, 4, 130, 7, 4, 4),
  (183, 'CA4878', 2450000, 13, 4, 132, 7, 4, 4),
  (184, 'CA1946', 2490000, 107, 4, 133, 7, 4, NULL),
  (185, 'ONE7558', 2500000, 36, 4, 11, 7, 4, NULL),
  (186, 'CA4179', 2498000, 75, 4, 134, 7, 4, NULL),
  (187, 'CA2830', 2500000, 67, 4, 135, 7, 4, 2),
  (188, 'CA4368', 2500000, 30, 4, 136, 7, 4, 3),
  (189, 'ONE8310', 2500000, 108, 4, 137, 7, 4, 4),
  (190, 'CA4326', 2500000, 109, 4, 138, 7, 4, 3),
  (191, 'CA2097', 2500000, 30, 4, 139, 7, 4, 4),
  (192, 'ONE8017', 2550000, 110, 4, 40, 7, 4, 15),
  (193, 'ONE8176', 2650000, 67, 4, 11, 7, 4, NULL),
  (194, 'CA3351', 2650000, 111, 4, 140, 7, 4, NULL),
  (195, 'CA2857', 2700000, 93, 4, 141, 7, 4, 4),
  (196, 'ONE6354', 2700000, 13, 4, 11, 7, 4, NULL),
  (197, 'ONE7183', 2700000, 112, 4, 142, 7, 4, 13),
  (198, 'ONE6636', 2790000, 57, 4, 11, 2, 4, 2),
  (199, 'CA1808', 2800000, 13, 4, 143, 7, 4, NULL),
  (200, 'ONE8327', 2800000, 113, 4, 144, 7, 4, 5),
  (201, 'ONE8193', 2900000, 30, 4, 145, 7, 4, 3),
  (202, 'ONE6695', 2900000, 81, 4, 11, 7, 4, 5),
  (203, 'ONE7484', 2950000, 114, 4, 146, 7, 4, NULL),
  (204, 'ONE6887', 2950000, 30, 4, 27, 7, 4, 3),
  (205, 'ONE8871', 2980000, 115, 4, 30, 7, 4, 4),
  (206, 'ONE7721', 2600000, 34, 4, 147, 7, 4, 1),
  (207, 'CA5028', 2995000, 30, 4, 148, 7, 4, 3),
  (208, 'ONE8836', 3000000, 116, 4, 149, 7, 4, 14),
  (209, 'ONE7103', 3000000, 79, 4, 150, 7, 4, 13),
  (211, 'ONE7858', 3074000, 13, 4, 151, 2, 4, 15),
  (212, 'CA1017', 3900000, 117, 4, 152, 7, 4, 17),
  (213, 'ONE8819', 3350000, 30, 4, 27, 7, 4, NULL),
  (214, 'CA2112', 3400000, 30, 4, 154, 7, 4, 4),
  (215, 'CA4281', 3395000, 30, 4, 155, 7, 4, 3),
  (216, 'ONE9157', 3500000, 118, 4, 156, 7, 4, 15),
  (217, 'ONE6995', 3500000, 119, 4, 11, 7, 4, NULL),
  (218, 'CA4554', 3500000, 30, 4, 157, 7, 4, NULL),
  (219, 'CA1512', 3500000, 45, 4, 158, 7, 4, 16),
  (220, 'ONE8132', 3500000, 86, 4, 159, 7, 4, 15),
  (221, 'CA4008', 3550000, 35, 4, 160, 7, 4, 2),
  (222, 'ONE6982', 3600000, 120, 4, 161, 6, 4, 13),
  (223, 'CA3423', 3750000, 67, 4, 162, 7, 4, NULL),
  (224, 'ONE7253', 3500000, 67, 4, 163, 7, 4, 5),
  (225, 'ONE7089', 3500000, 121, 4, 164, 7, 4, 16),
  (226, 'CA3038', 4000000, 30, 4, 165, 7, 4, 5),
  (227, 'ONE8216', 4200000, 101, 4, 18, 7, 4, NULL),
  (228, 'CA4929', 4280000, 57, 4, 166, 7, 4, NULL),
  (229, 'CA3185', 4300000, 115, 4, 167, 7, 4, 4),
  (230, 'CA0295', 4398000, 122, 4, 168, 2, 4, 15),
  (231, 'ONE6248', 4500000, 70, 4, 169, 7, 4, 14),
  (232, 'CA4277', 4500000, 123, 4, 170, 7, 4, NULL),
  (233, 'CA1657', 4500000, 124, 4, 171, 7, 4, 5),
  (234, 'ONE9033', 4650000, 86, 4, 172, 7, 4, 15),
  (235, 'CA4311', 4600000, 30, 4, 173, 7, 4, 3),
  (236, 'ONE7614', 4900000, 125, 4, 11, 7, 4, NULL),
  (237, 'CA2811', 4990000, 126, 4, 174, 7, 4, NULL),
  (238, 'CA2856', 5150000, 115, 4, 175, 7, 4, NULL),
  (239, 'ONE7971', 5300000, 86, 4, 176, 7, 4, 15),
  (240, 'CA5220', 5350000, 127, 4, 177, 7, 4, NULL),
  (241, 'ONE6674', 5500000, 128, 4, 178, 7, 4, NULL),
  (242, 'PR0007', 5600000, 129, 4, 179, 11, 4, NULL),
  (243, 'ONE5647', 5890000, 30, 4, 40, 7, 4, NULL),
  (244, 'ONE7171', 5900000, 130, 4, 180, 7, 4, 14),
  (245, 'TE0384', 6499000, 131, 4, 181, 3, 4, NULL),
  (246, 'ONE9470', 6500000, 86, 4, 182, 7, 4, 15),
  (247, 'ONE9185', 6999000, 132, 4, 183, 7, 4, 15),
  (248, 'CA3831', 7000000, 115, 4, 184, 7, 4, 14),
  (249, 'CA3740', 7000000, 133, 4, 185, 7, 4, 4),
  (250, 'CA3823', 7500000, 30, 4, 186, 7, 4, 3),
  (251, 'ONE6109', 11000000, 30, 4, 187, 7, 4, 5),
  (252, 'PR0013', 15100000, 37, 4, 40, 11, 4, NULL),
  (253, 'AR0032', 18000000, 85, 4, 188, 14, 4, NULL),
  (254, 'GA0124', 35000000, 134, 4, 189, 6, 4, 5),
  (255, 'ONE8749', 1100000, 80, 4, 190, 7, 4, 5),
  (256, 'ONE8337', 1290000, 31, 4, 11, 7, 4, 13),
  (257, 'ONE8466', 1490000, 57, 4, 192, 2, 4, 7),
  (258, 'ONE8744', 1499000, 136, 4, 193, 7, 4, NULL),
  (259, 'ONE9024', 1600000, 137, 4, 194, 7, 4, NULL),
  (261, 'ONE8633', 1690000, 13, 4, 11, 7, 4, NULL),
  (262, 'ONE8917', 1700000, 30, 4, 195, 7, 4, 3),
  (263, 'ONE8699', 1890000, 30, 4, 11, 7, 4, NULL),
  (264, 'ONE8695', 1900000, 139, 4, 11, 7, 4, NULL),
  (265, 'ONE8684', 1980000, 115, 4, 11, 7, 4, NULL),
  (266, 'ONE8531', 1950000, 140, 4, 196, 7, 4, 2),
  (267, 'ONE7529', 1898000, 30, 4, 197, 7, 4, 16),
  (268, 'ONE8673', 2390000, 141, 4, 11, 7, 4, NULL),
  (269, 'CA2796', 2300000, 38, 4, 198, 7, 4, 2),
  (270, 'ONE8682', 2580000, 67, 4, 11, 7, 4, NULL),
  (271, 'ONE8809', 2650000, 36, 4, 200, 7, 4, 7),
  (272, 'ONE8640', 2750000, 142, 4, 40, 7, 4, NULL),
  (273, 'ONE8700', 2790000, 30, 4, 11, 7, 4, NULL),
  (274, 'ONE8680', 3300000, 57, 4, 11, 2, 4, NULL),
  (275, 'ONE8688', 2950000, 101, 4, 11, 7, 4, NULL),
  (276, 'ONE8818', 2250000, 107, 4, 27, 7, 4, NULL),
  (277, 'ONE8679', 2990000, 143, 4, 11, 7, 4, NULL),
  (278, 'ONE8681', 4600000, 57, 4, 11, 2, 4, NULL),
  (279, 'ONE9110', 440000, 43, 4, 201, 10, 4, 2),
  (280, 'ONE8753', 800000, 144, 4, 202, 7, 4, 2),
  (281, 'ONE9551', 4000000, 35, 4, 203, 7, 4, 2),
  (282, 'ONE9566', 800000, 145, 4, 204, 3, 4, 3),
  (283, 'ONE7002', 1000000, 146, 4, 205, 7, 4, 5),
  (284, 'ONE9296', 2930000, 15, 4, 206, 7, 4, 4),
  (285, 'ONE7579', 1350000, 39, 4, 208, 7, 4, 7),
  (286, 'ONE9115', 2700000, 130, 4, 210, 7, 4, 15),
  (287, 'ONE9107', 1690000, 67, 4, 211, 7, 4, 15),
  (290, 'ONE9719', 9900000, 152, 4, 216, 7, 4, 5),
  (291, 'ONE9331', 850000, 153, 4, 217, 7, 4, 2),
  (292, 'ONE7387', 3300000, 30, 4, 218, 7, 4, NULL),
  (293, 'ONE8284', 920000, 19, 4, 11, 7, 4, 5),
  (294, 'ONE9077', 1980000, 154, 4, 30, 7, 4, 4),
  (295, 'ONE9658', 1250000, 156, 4, 219, 7, 4, 15),
  (296, 'ONE9698', 980000, 155, 4, 220, 7, 4, 15),
  (297, 'ONE5918', 355000, 100, 4, 11, 3, 4, 11),
  (298, 'ONE6687', 2490000, 157, 4, 11, 3, 4, 11),
  (299, 'ONE7940', 1400000, 30, 4, 222, 7, 4, 5),
  (300, 'ONE8203', 2340000, 158, 4, 11, 7, 4, 15),
  (301, 'ONE9807', 1200000, 159, 4, 223, 1, 4, 15),
  (302, 'ONE9813', 2300000, 30, 4, 225, 7, 4, 5),
  (303, 'ONE7924', 1650000, 100, 4, 56, 7, 4, 9),
  (304, 'ONE9788', 585000, 160, 4, 227, 1, 4, NULL),
  (305, 'ONE9654', 1200000, 44, 4, 228, 7, 4, 2),
  (306, 'ONE9815', 730000, 161, 4, 229, 7, 4, 5),
  (307, 'ONE8111', 3248000, 162, 4, 18, 7, 4, 11),
  (308, 'ONE9391', 6980000, 35, 4, 230, 7, 4, 5),
  (310, 'ONE9641', 2400000, 38, 4, 231, 7, 4, 1),
  (311, 'ONE5609', 2450000, 106, 4, 131, 7, 4, 5),
  (312, 'ONE9880', 4500000, 35, 4, 37, 7, 4, 1),
  (313, 'ONE9880', 4500000, 35, 4, 37, 7, 4, 1);

-- ─────────────────────────────────────────────────────────────────────
-- 1D. Dados originais das permutas (13 registros)
-- ─────────────────────────────────────────────────────────────────────

INSERT INTO stg_permuta_imovel (id, tipo_id, condominio, zona_id, cep, estado, cidade, bairro, endereco, valor, criado_por_id, proprietario_id, codigo, numero, corretor_id, ref) VALUES
  (10, 3, NULL, 4, '06656420', 'SP', 'Itapevi', 'Jardim da Rainha', 'Avenida Brasil', 192600, 4, 4, 'PM0001', NULL, 2, 'ONE6723'),
  (11, 1, NULL, 4, '06083080', 'SP', 'Osasco', 'Vila Osasco', 'Rua Itápolis', 360000, 4, 48, 'PM0002', NULL, 4, 'AP0466'),
  (12, 1, NULL, 4, '06040470', 'SP', 'Osasco', 'City Bussocaba', 'Rua Lázaro Suave', 479000, 4, 21, 'PM0003', NULL, 2, 'ONE6270'),
  (13, 13, NULL, 4, '18150000', NULL, NULL, NULL, NULL, 980000, 4, 66, 'PM0004', NULL, 13, 'ONE7433'),
  (14, 1, NULL, NULL, '05640001', 'SP', 'São Paulo', 'Jardim Londrina', 'Avenida Doutor Guilherme Dumont Vilares', 905000, 4, 67, 'PM0005', NULL, NULL, 'ONE9513'),
  (15, 7, NULL, 4, '06465903', 'SP', 'Barueri', 'Dezoito do Forte Empresarial/Alphaville.', 'Avenida Copacabana', 1200000, 4, 80, 'PM0006', NULL, 4, 'ONE9284'),
  (16, 2, NULL, 8, '11250970', 'SP', 'Bertioga', 'Centro', 'Avenida Anchieta', 1500000, 4, 90, 'PM0007', NULL, 4, 'ONE9241'),
  (17, 1, NULL, 4, '06026090', 'SP', 'Osasco', 'Vila Yara', 'Rua Doutor Paulo Ferraz da Costa Aguiar', 1950000, 4, 112, 'PM0008', NULL, 4, 'ONE9288'),
  (18, 13, NULL, 4, '18130000', NULL, NULL, NULL, NULL, 2350000, 4, 127, 'PM0009', NULL, 4, 'ONE7266'),
  (19, 6, NULL, 4, '06742004', 'SP', 'Vargem Grande Paulista', 'Chácara Belverde', 'Estrada Vicinal Municipal Ivo Mário Isaac Pires', 3157000, 4, 153, 'PM0010', NULL, 4, 'ONE9299'),
  (20, 1, NULL, 7, '05709040', 'SP', 'São Paulo', 'Vila Suzana', 'Rua Raimundo Simão de Souza', 2480000, 4, 199, 'PM0011', NULL, 4, 'ONE8497'),
  (21, 1, NULL, 7, NULL, 'SP', NULL, 'Jardim Paulista', NULL, 1345000, 4, 207, 'PM0012', NULL, NULL, 'ONE9615'),
  (22, 1, NULL, 4, NULL, NULL, NULL, NULL, NULL, 430000, 4, 209, 'PM0013', NULL, NULL, 'ONE9675');

-- ─────────────────────────────────────────────────────────────────────
-- 1E. Dados das lookup tables (secondMig/)
-- ─────────────────────────────────────────────────────────────────────

-- tipo_imovel (17 rows)
INSERT INTO stg_tipo_imovel (id, nome) VALUES
  (1, 'Apartamento'),
  (2, 'Casa'),
  (3, 'Terreno'),
  (4, 'Chacara'),
  (5, 'Comercial'),
  (6, 'Galpão'),
  (7, 'Casa em condomínio'),
  (8, 'Loja'),
  (9, 'Casa em condominio'),
  (10, 'Sala'),
  (11, 'Prédio Comercial'),
  (12, 'casa'),
  (13, 'Sitío'),
  (14, 'Área'),
  (15, 'Sitio'),
  (16, 'Sítio'),
  (17, 'Estúdio');

-- zona (11 rows)
INSERT INTO stg_zona (id, nome) VALUES
  (1, 'Sul'),
  (2, 'Norte'),
  (3, 'Leste'),
  (4, 'Oeste'),
  (5, 'Centro'),
  (6, 'Litoral Sudeste'),
  (7, 'São Paulo'),
  (8, 'Litoral Norte'),
  (9, 'Litoral Paulista'),
  (10, 'Litoral Sul'),
  (11, 'Sudeste');

-- tipo_automovel (3 rows)
INSERT INTO stg_tipo_automovel (id, nome) VALUES
  (1, 'Carro'),
  (2, 'Moto'),
  (3, 'Caminhao');

-- corretor (17 rows)
INSERT INTO stg_corretor (id, nome, telefone, email) VALUES
  (1, 'Marco', '11976120912', 'marco@oneconsultoriaimobiliaria.com.br'),
  (2, 'Cindy', '11950273823', 'cindy@oneconsultoriaimobiliaria.com.br'),
  (3, 'Wilson', '11931511578', 'wilson@oneconsultoriaimobiliaria.com.br'),
  (4, 'Larissa', '11954131900', 'larissa@oneconsultoriaimobiliaria.com.br'),
  (5, 'Rejane', '1145513617', 'rejane@oneconsultoriaimobiliaria.com.br'),
  (7, 'Ana Maria', '11997793225', 'anamaria@oneconsultoriaimobiliaria.com.br'),
  (9, 'Renata', '11998537754', 'renata@oneconsultoriaimobiliaria.com.br'),
  (11, 'Gilson', '11981243800', 'gilson@oneconsultoriaimobiliaria.com.br'),
  (12, 'Monica', '11975518400', 'monica@oneconsultoriaimobiliaria.com.br'),
  (13, 'Fernanda', '11996664323', 'fernanda@oneconsultoriaimobiliaria.com.br'),
  (14, 'Fabiana', '11948751000', 'fabiana@oneconsultoriaimobiliaria.com.br'),
  (15, 'Elisa', '11984200783', 'elisa@oneconsultoriaimobiliaria.com.br'),
  (16, 'Alessander', '11984428000', 'ale@oneconsultoriaimobiliaria.com.br'),
  (17, 'Victor', '11 98555.7005', 'victor@oneconsultoriaimobiliaria.com.br');

-- proprietario (231 rows)
INSERT INTO stg_proprietario (id, nome, telefone, email, corretor_id) VALUES
  (3, 'Alessandro', '11 99903.0816', 'ale.moraes@yahoo.com.br', NULL),
  (4, 'Fernando Azevedo de Pontes', '11 97365.2506', 'fenando_pontes@hotmail.com', NULL),
  (5, 'Alessandro', '11 99903.0816', 'ale.moraes@yahoo.com.br', NULL),
  (6, 'MOACYR FELIX', '11 95259.9861', 'comercial@skybox.eco.br', NULL),
  (7, 'Mauro Loureiro', '11 98680.2267', 'expansao.mauro@gmail.com', NULL),
  (8, 'Marina de Oliveira Lemos', '11 94131.3760', 'lemosma6@gmail.com', NULL),
  (9, 'Filipe Marques', '11 94898.0699', 'filipetafurimarques@yahoo.com.br', NULL),
  (10, 'Paula', '11 97494.1478', NULL, NULL),
  (11, 'MPM', '11 98193.8800', NULL, NULL),
  (12, 'Vanessa Monteiro Magro', '11 98895.2800', 'vmamarazzi@gmail.com', NULL),
  (13, 'Jane Gradícola e Sr. Gio', '11 99982.0275', 'janeladeirasilva@gmail.com', NULL),
  (14, 'Solange', '11 98010.0391', NULL, NULL),
  (15, 'Dora Bandeira', '11 94242.1110', NULL, NULL),
  (16, 'Ricardo', '11 99985.2852', NULL, NULL),
  (17, 'Lígia Migues', '11 98762.7286', NULL, NULL),
  (18, 'Gilson', '11 98124.3800', NULL, NULL),
  (19, 'Marina', '11 94131.3760', NULL, NULL),
  (20, 'Reginaldo', '11 99816.1883', NULL, NULL),
  (21, 'Diego', '11 99407.7629', NULL, NULL),
  (22, 'Gisele', '11 94453.0464', NULL, NULL),
  (23, 'Sandra', '11 95590.5322', NULL, NULL),
  (24, 'Tuka Rossatti', '11 99225.4321', NULL, NULL),
  (25, 'Sonia Regina de Oliveira Toffoli', '11 99902.6121', NULL, NULL),
  (26, 'Nestor', '11 7864.3681', NULL, NULL),
  (27, 'ANA KAN', '11 96587.0709', NULL, NULL),
  (28, 'ALEXANDRE', '11 98114.2357', NULL, NULL),
  (29, 'Adriana', '11 97105.5693', NULL, NULL),
  (30, 'Larissa', '11 95413.1900', NULL, NULL),
  (31, 'Monica', '11 97551.8400', NULL, NULL),
  (32, 'Leonardo Martins Marques e Karina Iris Rabello Ma', '11 97140.0558', NULL, NULL),
  (33, 'José Antônio Spacassassi', '11 97189.0344', NULL, NULL),
  (34, 'Miramon', '11 97424.4357', NULL, NULL),
  (35, 'Rita', '11 98831.7121', NULL, NULL),
  (36, 'Ana Carolina', '11 99601.8115', NULL, NULL),
  (37, 'Eduardo Quevedo', '11 97697.4100', NULL, NULL),
  (38, 'Dewar Benneshy', '11 97383.6980', NULL, NULL),
  (39, 'Rita de Cassia Monteiro Pereira', '11 99974.2209', NULL, NULL),
  (40, 'MPM', '11 8193.8800', NULL, NULL),
  (41, 'Fernando Azevedo de Pontes', '11 97365.2506', NULL, NULL),
  (42, 'Deborah Martinez Griebler', '11 97313.0266', NULL, NULL),
  (43, 'Roberta', '11 99627.8518', NULL, NULL),
  (44, 'Paula e Daniel', '11 99449.1722', NULL, NULL),
  (45, 'Mauro Loureiro', '11 98680.2267', NULL, NULL),
  (46, 'Vanessa Pereira dos Santos', '11 98595.1334', NULL, NULL),
  (47, 'Marcia Fernandes', '11 99966.9766', NULL, NULL),
  (48, 'Aline Lage', '11 97401.9618', NULL, NULL),
  (49, 'Rita', '11 4617.4484', NULL, NULL),
  (50, 'Douglas', '11 98444.3535', NULL, NULL),
  (51, 'João Machado', '11 98473.6769', NULL, NULL),
  (52, 'Gabrielly', '11 97306.4745', NULL, NULL),
  (53, 'Maria Luisa Simioni', '11 98736.2908', NULL, NULL),
  (54, 'Roseli e João Rodrigues', '11 94880.9006', NULL, NULL),
  (55, 'Leonardo Martins Marques e Karina Iris Rabello Ma', '11 97140.0558', NULL, NULL),
  (56, 'Renata Alves Silva', '11 95636.8088', NULL, NULL),
  (57, 'Maurício', '11 99803.0476', NULL, NULL),
  (58, 'Priscila', '11 99416.5930', NULL, NULL),
  (59, 'Leonor Magrini Trigo de Carvalho', '11 99443.4367', NULL, NULL),
  (60, 'Raquel Pedroso Wa Bronkers', '11 93804.5546', NULL, NULL),
  (61, 'Tatiana', '11 98272.9865', NULL, NULL),
  (62, 'Sergio', '11 99282.4509', NULL, NULL),
  (63, 'Nadja Nara', '11 99917.3933', NULL, NULL),
  (64, 'Fabiola', '11 97300.0573', NULL, NULL),
  (65, 'Emilio Gonçalvez Silva', '11 94376.9611', NULL, NULL),
  (66, 'Ademir Martins Silva', '11 99885.9677', NULL, NULL),
  (67, 'Fatima lucia mello', '11 99105.9312', NULL, NULL),
  (68, 'Anderson A Martins', '11 93926.2000', NULL, NULL),
  (69, 'Fabio', '18 99783.1777', NULL, NULL),
  (70, 'Danielle', '11 99568.9303', NULL, NULL),
  (71, 'Luiz Prado', '11 99440.9286', NULL, NULL),
  (72, 'Maryana', '11 99974.5344', NULL, NULL),
  (73, 'Felipe Ricardo Nucci', '11 99680.2084', NULL, NULL),
  (74, 'Iraja', '11 99651.9092', NULL, NULL),
  (75, 'Hilton', '11 99540.1210', NULL, NULL),
  (76, 'Fátima Conceição Silva', '11 99621.1468', NULL, NULL),
  (77, 'Wagner', '11 99686.3155', NULL, NULL),
  (78, 'Celso', '11 96393.8541', NULL, NULL),
  (79, 'Carlos Vettoreto', '11 98778.3636', NULL, NULL),
  (80, 'Carlos henrique', '11 98210.6494', NULL, NULL),
  (81, 'Fernanda', '11 99666.4323', NULL, NULL),
  (82, 'Henrique', '11 94732.0991', NULL, NULL),
  (83, 'Gustavo Martins', '11 94262.9530', NULL, NULL),
  (84, 'Nathaniel Rafael Dantas', '11 98175.4113', NULL, NULL),
  (85, 'Sérgio Tonzar', '11 94510.6886', NULL, NULL),
  (86, 'Maria Analia', '55 7448.0796', NULL, NULL),
  (87, 'Maria Analia', '55 7448.0796', NULL, NULL),
  (88, 'Fernando', '11 98100.1728', NULL, NULL),
  (89, 'Ivanir Vizoto e Luana', '11 99122.3377', NULL, NULL),
  (90, 'Ana Lúcia', '11 94790.8714', NULL, NULL),
  (91, 'Vera', '11 98416.4914', NULL, NULL),
  (92, 'Paulo', '11 99105.4571', NULL, NULL),
  (93, 'Eliane', '11 98334.5885', NULL, NULL),
  (94, 'Bela', '11 99197.4753', NULL, NULL),
  (95, 'Debora Santos/Rodrigo', '11 94760.0741', NULL, NULL),
  (96, 'Georg Zahn', '11 94522.0722', NULL, NULL),
  (97, 'Celeste', '11 99613.4322', NULL, NULL),
  (98, 'Marcelo dos Anjos', '11 95638.2123', NULL, NULL),
  (99, 'Eduardo Seigi', '11 99942.2046', NULL, NULL),
  (100, 'Abel Ferreira dos Santos', '11 99631.9339', NULL, NULL),
  (101, 'Edson Neves', '11 97676.7765', NULL, NULL),
  (102, 'Guto José', '11 94755.3398', NULL, NULL),
  (103, 'Sergio', '11 98823.4878', NULL, NULL),
  (104, 'Cindy', '11 96333.3327', NULL, NULL),
  (105, 'Adriana Gonçalvez', '11 97231.6874', NULL, NULL),
  (106, 'Meire', '11 98107.1670', NULL, NULL),
  (107, 'Neusa Tanaka', '11 91113.3738', NULL, NULL),
  (108, 'Cindy Kumagai', '11 98923.7042', NULL, NULL),
  (109, 'SILVIA FALCONI', '11 99960.2800', NULL, NULL),
  (110, 'Silvia', '11 99674.0694', NULL, NULL),
  (111, 'Fatima Corretora Casa Noble', '11 98254.6212', NULL, NULL),
  (112, 'Claudia Langone', '11 99365.1001', NULL, NULL),
  (113, 'Alessandra', '11 99648.4881', NULL, NULL),
  (114, 'Ramires', '11 98713.3516', NULL, NULL),
  (115, 'Célia Jampietro', '11 97300.4302', NULL, NULL),
  (116, 'Perciliana', '11 99630.2480', NULL, NULL),
  (117, 'João Augusto Simone', '11 98182.1011', NULL, NULL),
  (118, 'Roberta', '11 98162.6184', NULL, NULL),
  (119, 'Mauricio Marun', '11 99961.3566', NULL, NULL),
  (120, 'Rogerio', '11 97205.7044', NULL, NULL),
  (121, 'Angelo/Marcos Belfiori', '11 99985.4810', NULL, NULL),
  (122, 'Lilian Capotorto', '11 98271.3931', NULL, NULL),
  (123, 'Adriane Alves', '11 94008.0269', NULL, NULL),
  (124, 'Marcelo Ferreira Domingues', '11 96400.6000', NULL, NULL),
  (125, 'Caroline', '11 98171.6007', NULL, NULL),
  (126, 'Mirian', '11 99643.4631', NULL, NULL),
  (127, 'Priscila', '11 99473.7665', NULL, NULL),
  (128, 'Luiz Carlos/ Maria Tereza', '11 96191.4951', NULL, NULL),
  (129, 'Durval e Silvana', '11 97650.4128', NULL, NULL),
  (130, 'Elisangela', '11 96467.3314', NULL, NULL),
  (131, 'Hp Leticia Pierani', '11 98775.6488', NULL, NULL),
  (132, 'Silvana Araujo', '11 98221.6850', NULL, NULL),
  (133, 'Dr. Pedro Duarte', '11 97177.5000', NULL, NULL),
  (134, 'José Carlos e Rosa', '11 98287.0435', NULL, NULL),
  (135, 'Rosana', '11 99423.9116', NULL, NULL),
  (136, 'Fabiano e Fernanda', '11 94226.6647', NULL, NULL),
  (137, 'Pedro Requena', '11 98953.9947', NULL, NULL),
  (138, 'Fernando', '11 94751.2555', NULL, NULL),
  (139, 'Geraldo Aparecido Ferreira', '47 99912.2577', NULL, NULL),
  (140, 'Vilma', '11 94046.5952', NULL, NULL),
  (141, 'Amaro', '11 99413.6102', NULL, NULL),
  (142, 'Francisco', '11 99508.9230', NULL, NULL),
  (143, 'Giusepe', '11 99112.7141', NULL, NULL),
  (144, 'Tatiana', '11 99637.0041', NULL, NULL),
  (145, 'Alessandro', '11 99903.0816', NULL, NULL),
  (146, 'Renata', '11 99399.4610', NULL, NULL),
  (147, 'Renan', '31 9807.6657', NULL, NULL),
  (148, 'Tato e Renata', '11 97375.8535', NULL, NULL),
  (149, 'Gustavo Poletto', '18 99690.0107', NULL, NULL),
  (150, 'Sonia Maria Pizzi', '11 93392.5558', NULL, NULL),
  (151, 'Cristian', '11 95787.4889', NULL, NULL),
  (152, 'Teresa Caetano', '11 98255.0111', NULL, NULL),
  (153, 'Fulvio - Permuta Galpao - Maior Valor', '11 95934.3434', NULL, NULL),
  (154, 'Nelson e Beth', '11 97094.7766', NULL, NULL),
  (155, 'Sr Roland', '11 99962.9333', NULL, NULL),
  (156, 'Feres chaim Neto', '11 95249.0076', NULL, NULL),
  (157, 'Claudia', '11 99556.6867', NULL, NULL),
  (158, 'Alexandre Truffi', '11 98383.0963', NULL, NULL),
  (159, 'Luciano Romeu', '11 99600.2502', NULL, NULL),
  (160, 'Gilberto (Giba)', '11 97111.0909', NULL, NULL),
  (161, 'Sobek Empreendimentos Imobiliários Spe Ltda', '11 95374.8280', NULL, NULL),
  (162, 'Valdilene/Olimpio', '11 98284.3975', NULL, NULL),
  (163, 'Joaquin', '11 99610.7114', NULL, NULL),
  (164, 'Alfredo', '11 99982.7940', NULL, NULL),
  (165, 'Luciana Schwab', '11 96476.3674', NULL, NULL),
  (166, 'Sra Lenita', '11 99952.9672', NULL, NULL),
  (167, 'Alexandre Scolfaro', '11 98334.8081', NULL, NULL),
  (168, 'Clovis e Silvia', '11 4612.2793', NULL, NULL),
  (169, 'André Fiori Famá', '11 99966.0027', NULL, NULL),
  (170, 'Krauss', '11 98359.1010', NULL, NULL),
  (171, 'Paulo Sergio', '11 97673.8003', NULL, NULL),
  (172, 'Rodrigo', '11 98456.5780', NULL, NULL),
  (173, 'Waldir', '11 99257.0101', NULL, NULL),
  (174, 'Marcos', '11 99997.1115', NULL, NULL),
  (175, 'Wagner', '11 99686.3155', NULL, NULL),
  (176, 'Rejane', '11 99231.2567', NULL, NULL),
  (177, 'Charles', '11 91051.7924', NULL, NULL),
  (178, 'Diana Drawanz', '11 91555.8627', NULL, NULL),
  (179, 'Luis Henrique', '11 99916.8172', NULL, NULL),
  (180, 'Vanessa e Evandro', '11 99275.9900', NULL, NULL),
  (181, 'Renato Rouxinol', '11 98844.0132', NULL, NULL),
  (182, 'Junior Campos e Danieli', '11 98872.2141', NULL, NULL),
  (183, 'Neri', '11 98277.4004', NULL, NULL),
  (184, 'Luciana Sanches', '11 97415.2202', NULL, NULL),
  (185, 'Angelo/Marcos Belfiori', '11 99985.4810', NULL, NULL),
  (186, 'José Carlos', '11 99490.2318', NULL, NULL),
  (187, 'Rita de Cassia Monteiro Pereira', '11 99974.2209', NULL, NULL),
  (188, 'Joana Fontolan', '35 19167.7888', NULL, NULL),
  (189, 'Blanc Incorp', '11 98116.4594', NULL, NULL),
  (190, 'Michele Remax', '11 9830.8538', NULL, NULL),
  (191, 'Carlos Faria Porto State', '11 98336.3116', NULL, NULL),
  (192, 'Fabio Pereira e Odete', '11 98161.1221', NULL, NULL),
  (193, 'Percival', '11 98869.7553', NULL, NULL),
  (194, 'Silvia', '11 99812.2430', NULL, NULL),
  (195, 'Sergio', '11 99600.5512', NULL, NULL),
  (196, 'Sergio', '11 99521.6213', NULL, NULL),
  (197, 'Andrea', '11 97196.3867', NULL, NULL),
  (198, 'Marie Omi Ando', '11 99951.7253', NULL, NULL),
  (199, 'Miro', '11 99970.6536', NULL, NULL),
  (200, 'Edna', '11 96081.3281', NULL, NULL),
  (201, 'Wanderly Negrão', '11 99114.6026', NULL, NULL),
  (202, 'Hp Thalita Rugani Shiraishi', '11 98594.2745', NULL, NULL),
  (203, 'Gabriel Simão', '11 97596.6067', NULL, NULL),
  (204, 'Verônica', '11 99212.2452', NULL, NULL),
  (205, 'Cibele Gemelgo', '11 95777.4037', NULL, NULL),
  (206, 'Jane Gradícola e Sr. Gio', '11 99982.0275', NULL, NULL),
  (207, 'Yara Ferrauto', '11 98387.3157', NULL, NULL),
  (208, 'Sidney e Cidinha', '11 99198.5658', NULL, NULL),
  (209, 'Matheus Albino', '19 99885.0110', NULL, NULL),
  (210, 'Miriam', '11 99355.0479', NULL, NULL),
  (211, 'Andreza Pires', '11 95628.4315', NULL, NULL),
  (212, 'Teste PP', '11974693365', 'joaoraphaelsst@gmail.com', 4),
  (213, 'Natasha Bazhuni', '11910513878', NULL, NULL),
  (214, 'Natasha Bazhuni', '11910513878', NULL, NULL),
  (215, 'Natasha Bazhuni', '11910513878', NULL, NULL),
  (216, 'Natasha Bazhuni', '11910513878', NULL, NULL),
  (217, 'Milton', '11941853828', NULL, NULL),
  (218, 'Pedro Luiz Falcão', '11989286714', NULL, NULL),
  (219, 'Amanda', '11995973763', NULL, NULL),
  (220, 'Marco Aurelio Parretti', '11968858925', NULL, NULL),
  (221, 'Yoris', '11989128405', NULL, NULL),
  (222, 'Yoris', '11989128405', NULL, NULL),
  (223, 'Wigno Marteson', '11971301634', NULL, NULL),
  (224, 'Miguel', '11951987591', NULL, NULL),
  (225, 'Miguel', '11951987591', NULL, NULL),
  (226, 'Alex Vicente Guerra Alvarado e Barbara', '11992531472', NULL, NULL),
  (227, 'Alex Vicente Guerra Alvarado e Barbara', '11992531472', NULL, NULL),
  (228, 'Laura Vilela', '11998210840', NULL, NULL),
  (229, 'Celia', '1198735355', NULL, NULL),
  (230, 'Dewar Benneshy', '11973836980', NULL, NULL),
  (231, 'Felipe Lorenzoni', '11972719029', NULL, NULL),
  (232, 'Eurico', '11973380858', NULL, NULL);

-- condominio (159 rows)
INSERT INTO stg_condominio (id, nome, cep, estado, cidade, bairro, endereco, numero, km, valor_condominio) VALUES
  (5, 'São Paulo 2', '06706005', 'SP', 'Cotia', 'São Paulo II', 'Avenida Estácio de Sá', 1756, 26, 850),
  (6, 'Alpha Sitio Residencial', '06544300', 'SP', 'Santana de Parnaíba', 'Tamboré', NULL, 0, 0, 0),
  (7, 'Rejane', NULL, NULL, NULL, NULL, NULL, 0, 0, 0),
  (8, 'Shopping Boulevard Patio Paineiras', '06711250', 'SP', 'Cotia', 'Jardim da Glória', NULL, 0, 0, 0),
  (9, 'Reserva Santa Paula - Km 32', '06716500', 'SP', 'Cotia', 'Parque Dom Henrique', NULL, 0, 0, 0),
  (10, 'Vale do Rio Cotia - Km 23', '06355400', 'SP', 'Carapicuíba', 'Chácara Vale do Rio Cotia', NULL, 0, 0, 0),
  (11, 'Quinta de São Fernando - Km 28', '06704500', 'SP', 'Cotia', 'Pitas', NULL, 0, 0, 0),
  (12, 'Vale do Rio Cotia - Km 23', '06355400', 'SP', 'Carapicuíba', 'Chácara Vale do Rio Cotia', NULL, 0, 0, 0),
  (13, 'Fazendinha - Km 23', '06351040', 'SP', 'Carapicuíba', 'Pousada dos Bandeirantes', NULL, 0, 0, 0),
  (14, 'Jardim das Flores - Km 26', '06713630', 'SP', 'Cotia', 'Jardim São Vicente', NULL, 0, 0, 0),
  (15, 'Jardim Mediterrâneo - Km 24', '06708722', 'SP', 'Cotia', 'Parque Silvino Pereira', NULL, 0, 0, 0),
  (16, 'Pinus Park - Km 23', '06710660', 'SP', 'Cotia', 'Horizontal Park', NULL, 0, 0, 0),
  (17, 'Queluz Vita - Km 21', '06710500', 'SP', 'Cotia', 'Chácara Pavoeiro', NULL, 0, 0, 0),
  (18, 'Terras do Madeira - Fazendinha - Km 23', '06351040', 'SP', 'Carapicuíba', 'Pousada dos Bandeirantes', NULL, 0, 0, 0),
  (19, 'Villaggio Viana - Km 22', '06709300', 'SP', 'Cotia', 'Granja Viana', NULL, 0, 0, 0),
  (20, 'Village Los Angeles - Km 26', '06713100', 'SP', 'Cotia', 'Jardim Torino', NULL, 0, 0, 0),
  (21, 'Prime Office Park - Km 23', '06710700', 'SP', 'Cotia', 'Jardim Lambreta', NULL, 0, 0, 0),
  (22, 'Boulevard Granja Viana - Km 22', '06709285', 'SP', 'Cotia', 'Granja Viana', NULL, 0, 0, 0),
  (23, 'Residencial Passeio de Bussocaba', '06040470', 'SP', 'Osasco', 'City Bussocaba', NULL, 0, 0, 0),
  (24, 'Condomínio Mar Aberto Il', '11730000', NULL, NULL, NULL, NULL, 0, 0, 0),
  (25, 'Reserva Samambaia', '06721100', 'SP', 'Cotia', 'Portal do Santa Paula', NULL, 0, 0, 0),
  (26, 'Residencial do Bosque - Km 21', '06710400', 'SP', 'Cotia', 'Jardim Barbacena', NULL, 0, 0, 0),
  (27, 'Nova Vianna - Km 26', '06715400', 'SP', 'Cotia', 'Paisagem Renoir', NULL, 0, 0, 0),
  (28, 'Gramado - Km 21', '06710040', 'SP', 'Cotia', 'Gramado', NULL, 0, 0, 0),
  (29, 'Moradas do Sol - Km 28', '06704485', 'SP', 'Cotia', 'Portal Roselândia', NULL, 0, 0, 0),
  (30, 'São Paulo 2 - Km 26', '06706005', 'SP', 'Cotia', 'São Paulo II', NULL, 0, 0, 0),
  (31, 'Vila Verde (antigo Transurb) - Km 36', '06670330', NULL, NULL, NULL, NULL, 0, 0, 0),
  (32, 'Parque Frondoso - Km 22', '06709300', 'SP', 'Cotia', 'Granja Viana', NULL, 0, 0, 0),
  (33, 'Reserva da Granja Viana - Km 25', '06712150', 'SP', 'Cotia', 'Jardim Passárgada I', NULL, 0, 0, 0),
  (34, 'Golf Village - Km 23', '06351040', 'SP', 'Carapicuíba', 'Pousada dos Bandeirantes', NULL, 0, 0, 0),
  (35, 'Vintage - Km 26', '06715410', 'SP', 'Cotia', 'Paisagem Renoir', NULL, 0, 0, 0),
  (36, 'Chácaras do Lago - Km 23', '06345290', 'SP', 'Carapicuíba', 'Chácara São João', NULL, 0, 0, 0),
  (37, 'Prédio Comercial - Km 22', '06710700', 'SP', 'Cotia', 'Jardim Lambreta', NULL, 0, 0, 0),
  (38, 'Parque Das Artes - Km 26', '06846500', 'SP', 'Embu das Artes', 'Jardim Indaiá', NULL, 0, 0, 0),
  (39, 'Jardim Das Paineiras - Km 23', '06711020', 'SP', 'Cotia', 'Bosque do Vianna', NULL, 0, 0, 0),
  (40, 'Residence Plaza - Km 26', '06707100', 'SP', 'Cotia', 'Granja Viana II', NULL, 0, 0, 0),
  (41, 'Villa Vianna - Km 23', '06711020', 'SP', 'Cotia', 'Bosque do Vianna', NULL, 0, 0, 0),
  (42, 'Terreno de Rua - Itapevi', '06656420', 'SP', 'Itapevi', 'Jardim da Rainha', NULL, 0, 0, 0),
  (43, 'Vintage Office - Km 26', '06713630', 'SP', 'Cotia', 'Jardim São Vicente', NULL, 0, 0, 0),
  (44, 'Villa D Este - Km 31', '06705050', 'SP', 'Cotia', 'Jardim Caiapiá', NULL, 0, 0, 0),
  (45, 'Recanto Suíço - Km 39', '06727190', 'SP', 'Cotia', 'Jardim dos Pereiras (Caucaia do Alto)', NULL, 0, 0, 0),
  (46, 'Inspire Barueri - Flores / Verde', '06401015', 'SP', 'Barueri', 'Centro', NULL, 0, 0, 0),
  (47, 'Terreno de Rua - Km 31', '06716302', 'SP', 'Cotia', 'Parque Dom Henrique', NULL, 0, 0, 0),
  (48, 'Vila de Espanha - Km 21', '06710540', 'SP', 'Cotia', 'Jardim Guerreiro', NULL, 0, 0, 0),
  (49, 'Florada Raízes - Loteamento', '06726471', 'SP', 'Cotia', 'Água Espraiada (Caucaia do Alto)', NULL, 0, 0, 0),
  (50, 'Florada Raízes - Loteamento', '06726471', 'SP', 'Cotia', 'Água Espraiada (Caucaia do Alto)', NULL, 0, 0, 0),
  (51, 'Alpha View', '06414000', 'SP', 'Barueri', 'Jardim Tupanci', NULL, 0, 0, 0),
  (52, 'Grand Club Cotia', '06716769', 'SP', 'Cotia', 'Nakamura Park', NULL, 0, 0, 0),
  (53, 'Condomínio Cidade Jardim', '06709320', 'SP', 'Cotia', 'Granja Viana', NULL, 0, 0, 0),
  (54, 'Vila dos Pinus - Km 21', '06710450', 'SP', 'Cotia', 'Jardim Barbacena', NULL, 0, 0, 0),
  (55, 'Quinta dos Lagos - Km 28', '06704500', 'SP', 'Cotia', 'Pitas', NULL, 0, 0, 0),
  (56, 'Viva Vida - Km 29', '06715400', NULL, NULL, NULL, NULL, 0, 0, 0),
  (57, 'Miolo Granja Viana - Km 23', '06708620', 'SP', 'Cotia', 'Chácara Eliana', NULL, 0, 0, 0),
  (58, 'Residencial Gramado', '06710280', 'SP', 'Cotia', 'Gramado', NULL, 0, 0, 0),
  (59, 'Rua Poços de Caldas, nº 113, Jardim Sabiá, Cotia', '06716558', 'SP', 'Cotia', 'Jardim Sabiá', NULL, 0, 0, 0),
  (60, 'Recanto Das Flores - Km 28', '06705490', 'SP', 'Cotia', 'Parque Rincão', NULL, 0, 0, 0),
  (61, 'Colinas de Caucaia do Alto - Km 39', '06727400', 'SP', 'Cotia', 'Colina (Caucaia do Alto)', NULL, 0, 0, 0),
  (62, 'Reserva Vale Verde - Km 28', '06705230', 'SP', 'Cotia', 'Jardim Caiapiá', NULL, 0, 0, 0),
  (63, 'Terreno de Rua', '06710500', 'SP', 'Cotia', 'Chácara Pavoeiro', NULL, 0, 0, 0),
  (64, 'Residencial Vila Real - Km 39', '06730000', NULL, NULL, NULL, NULL, 0, 0, 0),
  (65, 'Terreno Residencial - Km 22', '06721470', 'SP', 'Cotia', 'Chácara Rincão', NULL, 0, 0, 0),
  (66, 'Paysage Serein - Km 42', '06730000', NULL, NULL, NULL, NULL, 0, 0, 0),
  (67, 'Nova Higienópolis - Km 28', '06642000', 'SP', 'Jandira', 'Jardim do Golf I', NULL, 0, 0, 0),
  (68, 'San Remo - Km 28', '06703600', 'SP', 'Cotia', 'Jardim Maria Tereza', NULL, 0, 0, 0),
  (69, 'The Square Village - Km 22', '06709360', 'SP', 'Cotia', 'Jardim Semiramis', NULL, 0, 0, 0),
  (70, 'Recanto Verde - Km 23', '06351220', 'SP', 'Carapicuíba', 'Chácara Moinho Velho', NULL, 0, 0, 0),
  (71, 'Vila Velha - Km 23', '06355240', 'SP', 'Carapicuíba', 'Jardim Ana Estela', NULL, 0, 0, 0),
  (72, 'Paysage Clair - Km 39', '06738276', 'SP', 'Vargem Grande Paulista', 'San Diego', NULL, 0, 0, 0),
  (73, 'Paysage Bella Vitta - Km 42', '06730000', NULL, NULL, NULL, NULL, 0, 0, 0),
  (74, 'Paisagem Renoir II e III - Km 26', '06715400', 'SP', 'Cotia', 'Paisagem Renoir', NULL, 0, 0, 0),
  (75, 'Residencial Jardim da Glória - km 25', '06711150', 'SP', 'Cotia', 'Jardim da Glória', NULL, 0, 0, 0),
  (76, 'Palm Hills - Km 26', '06715410', 'SP', 'Cotia', 'Paisagem Renoir', NULL, 0, 0, 0),
  (77, 'Casa de rua', '06707340', 'SP', 'Cotia', 'Granja Viana II', NULL, 0, 0, 0),
  (78, 'Vila Real do Moinho Velho - Km 26', '06805235', 'SP', 'Embu das Artes', 'Moinho Velho', NULL, 0, 0, 0),
  (79, 'Haras Bela Vista - Km 42', '06730000', NULL, NULL, NULL, NULL, 0, 0, 0),
  (80, 'Granja Caiapiá - Km 28', '06704565', 'SP', 'Cotia', 'Granja Caiapiá', NULL, 0, 0, 0),
  (81, 'Granja Viana II - Gleba 1 e 2 - Km 26', '06707350', 'SP', 'Cotia', 'Granja Viana II', NULL, 0, 0, 0),
  (82, 'Villanova - Km 23', '06710700', 'SP', 'Cotia', 'Jardim Lambreta', NULL, 0, 0, 0),
  (83, 'Pinheiros Tenis Village - Km 39', '06727500', 'SP', 'Cotia', 'Pinheiros Tênis Village', NULL, 0, 0, 0),
  (84, 'Jardim Passárgada B - Km 25', '06712116', 'SP', 'Cotia', 'Jardim Passárgada I', NULL, 0, 0, 0),
  (85, 'Área - Km 22', '06709180', 'SP', 'Cotia', 'Chácaras do Refúgio-Granja Viana', NULL, 0, 0, 0),
  (86, 'Alphaville Granja Viana - Km 23', '06345710', 'SP', 'Carapicuíba', 'Granja Viana', NULL, 0, 0, 0),
  (87, 'Casa de rua', '06350280', 'SP', 'Carapicuíba', 'Jardim Colonial', NULL, 0, 0, 0),
  (88, 'Jardim dos Ipês - Km 31', '06716160', 'SP', 'Cotia', 'Jardim dos Ipês', NULL, 0, 0, 0),
  (89, 'Reserva do Moinho - Fazendinha - Km 23', '06351220', 'SP', 'Carapicuíba', 'Chácara Moinho Velho', NULL, 0, 0, 0),
  (90, 'São Fernando Residência - Km 28', '06449300', 'SP', 'Barueri', 'Parque Viana', NULL, 0, 0, 0),
  (91, 'Jardim Passárgada A - Km 25', '06712116', 'SP', 'Cotia', 'Jardim Passárgada I', NULL, 0, 0, 0),
  (92, 'Vila Moura - Fazendinha - Km 23', '06351110', 'SP', 'Carapicuíba', 'Chácara Santa Lúcia', NULL, 0, 0, 0),
  (93, 'Granja Viana Ii - Glebas 4 e 5 - Km 26', '06707100', 'SP', 'Cotia', 'Granja Viana II', NULL, 0, 0, 0),
  (94, 'Terreno Miolo Granja Viana - Km 23', '06708620', 'SP', 'Cotia', 'Chácara Eliana', NULL, 0, 0, 0),
  (95, 'Jardim Colonial - Chácara São João - Km 23', '06350270', 'SP', 'Carapicuíba', 'Chácara de La Rocca', NULL, 0, 0, 0),
  (96, 'Meu Recanto', '06845210', 'SP', 'Embu das Artes', 'Jardim dos Ipês', NULL, 0, 0, 0),
  (97, 'Área - Km 31', '06851450', 'SP', 'Itapecerica da Serra', 'Engenho', NULL, 0, 0, 0),
  (98, 'Casa de Rua', '06708360', 'SP', 'Cotia', 'Vila Santo Antônio', NULL, 0, 0, 0),
  (99, 'Euroville - Km 23', '06355462', 'SP', 'Carapicuíba', 'Residencial Euroville', NULL, 0, 0, 0),
  (100, 'Jardim Colibri - Km 26', '06713600', 'SP', 'Cotia', 'Jardim Colibri', NULL, 0, 0, 0),
  (101, 'Recanto Inpla - Km 23', '06350190', 'SP', 'Carapicuíba', 'Recanto Impla', NULL, 0, 0, 0),
  (102, 'Beverly Hills - Km 28', '06620400', 'SP', 'Jandira', 'Parque Nova Jandira', NULL, 0, 0, 0),
  (103, 'Granja Viana Ii - Glebas 4 e 5 - Km 26', '06707100', 'SP', 'Cotia', 'Granja Viana II', NULL, 0, 0, 0),
  (104, 'Avenida Marginal', '06708030', 'SP', 'Cotia', 'Parque São George', NULL, 0, 0, 0),
  (105, 'Central Park Residence - Km 45', '06730000', NULL, NULL, NULL, NULL, 0, 0, 0),
  (106, 'Raizes Granja Viana - Km 23', '06711020', 'SP', 'Cotia', 'Bosque do Vianna', NULL, 0, 0, 0),
  (107, 'Forest Hills - Km 28', '06630010', 'SP', 'Jandira', 'Altos de São Fernando', NULL, 0, 0, 0),
  (108, 'Parque Frondoso - Km 22', '06709300', 'SP', 'Cotia', 'Granja Viana', NULL, 0, 0, 0),
  (109, 'Jardim Passárgada D - Km 25', '06712116', 'SP', 'Cotia', 'Jardim Passárgada I', NULL, 0, 0, 0),
  (110, 'Jardim Passárgada E - Km 25', '06712116', 'SP', 'Cotia', 'Jardim Passárgada I', NULL, 0, 0, 0),
  (111, 'Reserva Santa Maria - Km 28', '06642000', 'SP', 'Jandira', 'Jardim do Golf I', NULL, 0, 0, 0),
  (112, 'Paysage Noble - Km 39', '06738196', 'SP', 'Vargem Grande Paulista', 'San Diego', NULL, 0, 0, 0),
  (113, 'Reserva Santa Maria - Km 28', '06642000', 'SP', 'Jandira', 'Jardim do Golf I', NULL, 0, 0, 0),
  (114, 'Aldeia da Fazendinha - Km 23', '06364000', 'SP', 'Carapicuíba', 'Jardim Ana Estela', NULL, 0, 0, 0),
  (115, 'Palos Verdes - Km 23', '06709150', 'SP', 'Cotia', 'Granja Viana', NULL, 0, 0, 0),
  (116, 'Condomínio Chacara dos Lagos - Km 23', '06345300', 'SP', 'Carapicuíba', 'Chácara dos Lagos', NULL, 0, 0, 0),
  (117, 'Granja Velha - Km 24', '06708415', 'SP', 'Cotia', 'Vila Santo Antônio', NULL, 0, 0, 0),
  (118, 'Outeiro de São Fernando', '06447445', 'SP', 'Barueri', 'Outeiro do São Fernando', NULL, 0, 0, 0),
  (119, 'Dom Henrique II - Km 31', '06716250', 'SP', 'Cotia', 'Jardim Ipês', NULL, 0, 0, 0),
  (120, 'Condomínio Polo 40 - Km 40', '06730000', NULL, NULL, NULL, NULL, 0, 0, 0),
  (121, 'Alphaville 5', '06539005', 'SP', 'Santana de Parnaíba', 'Alphaville', NULL, 0, 0, 0),
  (122, 'Casa de Rua - Km 23', '06708420', 'SP', 'Cotia', 'Vila Santo Antônio', NULL, 0, 0, 0),
  (123, 'Horizontal Park - Km 23', '06710660', 'SP', 'Cotia', 'Horizontal Park', NULL, 0, 0, 0),
  (124, 'São Fernando Golf Club - Km 28', '06705490', 'SP', 'Cotia', 'Parque Rincão', NULL, 0, 0, 0),
  (125, 'Villagio Toscano - Chácaras do Lago -  Km 23', '06345320', 'SP', 'Carapicuíba', 'Chácara dos Lagos', NULL, 0, 0, 0),
  (126, 'Bosque do Vianna - Km 23', '06711020', 'SP', 'Cotia', 'Bosque do Vianna', NULL, 0, 0, 0),
  (127, 'Residencial Villa Solaia', '06458265', 'SP', 'Barueri', 'Tamboré', NULL, 0, 0, 0),
  (128, 'Residencial Alphaville 10', '06539005', 'SP', 'Santana de Parnaíba', 'Alphaville', NULL, 0, 0, 0),
  (129, 'Prédio Comercial - Km 23', '06709150', 'SP', 'Cotia', 'Granja Viana', NULL, 0, 0, 0),
  (130, 'Parque Primavera - Km 22', '06709300', 'SP', 'Cotia', 'Granja Viana', NULL, 0, 0, 0),
  (131, 'Terreno de Rua - Km 22', '06708420', 'SP', 'Cotia', 'Vila Santo Antônio', NULL, 0, 0, 0),
  (132, 'Jardim Colonial - Chácara São João - Km 23', '06350270', 'SP', 'Carapicuíba', 'Chácara de La Rocca', NULL, 0, 0, 0),
  (133, 'Haras Guancan - Km 26', '06713100', 'SP', 'Cotia', 'Jardim Torino', NULL, 0, 0, 0),
  (134, 'Galpão - Km 30', '06714150', 'SP', 'Cotia', 'Parque Alexandre', NULL, 0, 0, 0),
  (135, 'Jardim Amanda - Fazendinha - Km 23', '06351170', 'SP', 'Carapicuíba', 'Granja Santa Maria', NULL, 0, 0, 0),
  (136, 'Reserva dos Pinheiros - km 23', '06355240', 'SP', 'Carapicuíba', 'Jardim Ana Estela', NULL, 0, 0, 0),
  (137, 'Petit Village - Km 21', '06710500', 'SP', 'Cotia', 'Chácara Pavoeiro', NULL, 0, 0, 0),
  (138, 'Reserva Pinus Park - Km 23', '06710663', 'SP', 'Cotia', 'Pinus Park', NULL, 0, 0, 0),
  (139, 'Vila Real do Moinho Velho - Km 26', '06805235', 'SP', 'Embu das Artes', 'Moinho Velho', NULL, 0, 0, 0),
  (140, 'Residencial Willy - Fazendinha - Km 23', '06351210', 'SP', 'Carapicuíba', 'Chácara das Candeias', NULL, 0, 0, 0),
  (141, 'Granja do Lago - Km 23', '06709220', 'SP', 'Cotia', 'Chácara Granja Velha', NULL, 0, 0, 0),
  (142, 'Chácara Santa Lúcia - Fazendinha - Km 23', '06351040', 'SP', 'Carapicuíba', 'Pousada dos Bandeirantes', NULL, 0, 0, 0),
  (143, 'Jardim Passárgada C -  Km 25', '06712116', 'SP', 'Cotia', 'Jardim Passárgada I', NULL, 0, 0, 0),
  (144, 'Colinas de São Fernando - Km 28', '06704400', 'SP', 'Cotia', 'Chácaras Roselândia', NULL, 0, 0, 0),
  (145, 'Vitta Granja Viana - Km 30', '06714150', 'SP', 'Cotia', 'Parque Alexandre', NULL, 0, 0, 0),
  (146, 'Villagio da Granja -  Km 21', '06710400', 'SP', 'Cotia', 'Jardim Barbacena', NULL, 0, 0, 0),
  (147, 'Condo Teste', '06709150', 'SP', 'Cotia', 'Granja Viana', 'Avenida São Camilo', 1491, 21, 500),
  (148, 'Teste2 Condo', NULL, NULL, NULL, NULL, NULL, 0, 21, 500),
  (149, 'Teste3 Condo', '06709150', 'SP', 'Cotia', 'Granja Viana', 'Avenida São Camilo', 0, 21, 500),
  (150, 'testeformcondo', '06709150', 'SP', 'Cotia', 'Granja Viana', NULL, 0, 0, 0),
  (151, 'teste', '06709150', 'SP', 'Cotia', 'Granja Viana', NULL, 0, 0, 0),
  (152, 'Alphaville Residencial 1', '06454040', 'SP', 'Barueri', 'Alphaville Centro Industrial e Empresarial/Alphaville.', 'Alameda Mamoré', 1500, 23, 1400),
  (153, 'Jardim Das Acácias - Km 25', '06711340', 'SP', 'Cotia', 'Chácara Canta Galo', 'Rua Maracatu', 448, 25, 62500),
  (154, 'Pousada dos Bandeirantes - Km 23', '06351020', 'SP', 'Carapicuíba', 'Pousada dos Bandeirantes', 'Rua Fernão Dias Paes Leme', 350, 23, 168400),
  (155, 'Maderá - Km 28', '06705490', 'SP', 'Cotia', 'Parque Rincão', 'Estrada Fernando Nobre', NULL, 28, 1000),
  (156, 'Modern Townhouse Granja Viana - Km 23', '06709150', 'SP', 'Cotia', 'Granja Viana', 'Avenida São Camilo', 1647, 23, 1000),
  (157, 'Terreno de Rua - Km 22', '06709180', 'SP', 'Cotia', 'Chácaras do Refúgio-Granja Viana', 'Estrada Zurique', 205, 22, NULL),
  (158, 'Chácara Das Paineiras 2 - Km 23', '06364300', 'SP', 'Carapicuíba', 'Chácara das Paineiras', 'Rua Jupi', 1, 23, 91954),
  (159, 'Aruanã 601', '06460010', 'SP', 'Barueri', 'Tamboré', 'Avenida Aruanã', 601, NULL, 97800),
  (160, 'Condomínio Ed. Viena', '06083160', 'SP', 'Osasco', 'Vila Osasco', 'Rua Antônia Bizarro', 6, NULL, 950000),
  (161, 'Villaggio Felicitá - Km 26', '06707035', 'SP', 'Cotia', 'Granja Viana II', 'Rua Anésia Cardoso de Carvalho', NULL, 26, 80000),
  (162, 'Orvalho Granja Viana - Km 23', '06711020', 'SP', 'Cotia', 'Bosque do Vianna', 'Alameda Tangará', 775, 23, 310000);


-- ═════════════════════════════════════════════════════════════════════
-- ETAPA 2: Mapeamentos Corretos
-- ═════════════════════════════════════════════════════════════════════
-- Fase 1 inferiu tipos a partir de prefixos de ref. Agora temos as
-- lookup tables reais. Mapeamos para valores compatíveis com o enum
-- erp.tipo_imovel: casa, apartamento, terreno, comercial, rural, outro

CREATE TEMP TABLE tipo_imovel_correct (
  old_id INTEGER PRIMARY KEY,
  novo_tipo TEXT NOT NULL,
  nome_original TEXT
);

INSERT INTO tipo_imovel_correct VALUES
  -- old_id, valor normalizado, nome original no sistema antigo
  (1,  'apartamento', 'Apartamento'),
  (2,  'casa',        'Casa'),
  (3,  'terreno',     'Terreno'),
  (4,  'rural',       'Chacara'),
  (5,  'comercial',   'Comercial'),
  (6,  'comercial',   'Galpão'),
  (7,  'casa',        'Casa em condomínio'),    -- Fase 1: 'casa' ✓
  (8,  'comercial',   'Loja'),                  -- Fase 1: 'rural' ✗ → 'comercial'
  (9,  'casa',        'Casa em condominio'),    -- Fase 1: 'comercial' ✗ → 'casa'
  (10, 'comercial',   'Sala'),                  -- Fase 1: 'apartamento' ✗ → 'comercial'
  (11, 'comercial',   'Prédio Comercial'),      -- Fase 1: 'comercial' ✓
  (12, 'casa',        'casa'),
  (13, 'rural',       'Sitío'),                 -- Fase 1: 'rural' ✓
  (14, 'terreno',     'Área'),                  -- Fase 1: 'terreno' ✓
  (15, 'rural',       'Sitio'),
  (16, 'rural',       'Sítio'),
  (17, 'apartamento', 'Estúdio');

CREATE TEMP TABLE zona_correct (
  old_id INTEGER PRIMARY KEY,
  nova_zona TEXT NOT NULL,
  nome_original TEXT
);

INSERT INTO zona_correct VALUES
  -- old_id, valor normalizado, nome original
  (1,  'sul',              'Sul'),              -- Fase 1: 'norte' ✗
  (2,  'norte',            'Norte'),
  (3,  'leste',            'Leste'),
  (4,  'oeste',            'Oeste'),            -- Fase 1: 'oeste' ✓
  (5,  'centro',           'Centro'),
  (6,  'litoral_sudeste',  'Litoral Sudeste'),  -- Fase 1: 'sul' ✗
  (7,  'sao_paulo',        'São Paulo'),        -- Fase 1: 'leste' ✗
  (8,  'litoral_norte',    'Litoral Norte'),    -- Fase 1: 'norte' ✗
  (9,  'litoral_paulista', 'Litoral Paulista'),
  (10, 'litoral_sul',      'Litoral Sul'),
  (11, 'sudeste',          'Sudeste');

CREATE TEMP TABLE tipo_automovel_correct (
  old_id INTEGER PRIMARY KEY,
  novo_tipo TEXT NOT NULL
);

INSERT INTO tipo_automovel_correct VALUES
  (1, 'carro'),
  (2, 'moto'),
  (3, 'caminhao');


-- ═════════════════════════════════════════════════════════════════════
-- ETAPA 3: Corrigir tipo_imovel nos ativos
-- ═════════════════════════════════════════════════════════════════════
-- JOIN via ref para obter o tipo_id original, aplicar mapeamento correto.
-- Refs duplicados têm mesmo tipo_id, então o resultado é determinístico.

-- 3A. Imóveis (264 registros)
UPDATE erp.ativos a
SET tipo_imovel = tic.novo_tipo
FROM stg_imovel si
JOIN tipo_imovel_correct tic ON si.tipo_id = tic.old_id
WHERE a.ref = si.ref
  AND a.natureza = 'imovel'
  AND a.titulo_anuncio LIKE '[MOCK]%';

-- 3B. Permutas (13 registros)
UPDATE erp.ativos a
SET tipo_imovel = tic.novo_tipo
FROM stg_permuta_imovel sp
JOIN tipo_imovel_correct tic ON sp.tipo_id = tic.old_id
WHERE a.ref = sp.ref
  AND a.natureza = 'permuta_imovel';


-- ═════════════════════════════════════════════════════════════════════
-- ETAPA 4: Corrigir zona nos ativos
-- ═════════════════════════════════════════════════════════════════════

-- 4A. Imóveis
UPDATE erp.ativos a
SET zona = zc.nova_zona
FROM stg_imovel si
JOIN zona_correct zc ON si.zona_id = zc.old_id
WHERE a.ref = si.ref
  AND a.natureza = 'imovel'
  AND a.titulo_anuncio LIKE '[MOCK]%'
  AND si.zona_id IS NOT NULL;

-- 4B. Permutas
UPDATE erp.ativos a
SET zona = zc.nova_zona
FROM stg_permuta_imovel sp
JOIN zona_correct zc ON sp.zona_id = zc.old_id
WHERE a.ref = sp.ref
  AND a.natureza = 'permuta_imovel'
  AND sp.zona_id IS NOT NULL;


-- ═════════════════════════════════════════════════════════════════════
-- ETAPA 5: Substituir "Corretor #N" por nomes reais
-- ═════════════════════════════════════════════════════════════════════

-- 5A. Substituir com nome real do corretor
UPDATE erp.ativos a
SET corretor = sc.nome
FROM stg_corretor sc
WHERE a.corretor = 'Corretor #' || sc.id;

-- 5B. Limpar "Corretor #0" (corretor_id era NULL no sistema antigo)
UPDATE erp.ativos
SET corretor = NULL
WHERE corretor = 'Corretor #0';


-- ═════════════════════════════════════════════════════════════════════
-- ETAPA 6: Corrigir tipo_imovel e zona dentro do JSONB interesses
-- ═════════════════════════════════════════════════════════════════════
-- Usa substituição in-place no JSONB. As substituições são seguras pois:
--   'comercial' em interesses → só veio de tipo_id=9 (Casa condomínio) → 'casa'
--   'rural' em interesses     → só veio de tipo_id=8 (Loja)           → 'comercial'
--   'norte' em interesses     → só veio de zona_id=1 (Sul)            → 'sul'
--   'sul' em interesses       → só veio de zona_id=6 (Litoral SE)     → 'litoral_sudeste'
--   'leste' em interesses     → só veio de zona_id=7 (São Paulo)      → 'sao_paulo'
-- Nenhuma ambiguidade nos dados reais de interesses.

UPDATE erp.ativos a
SET interesses = (
  SELECT COALESCE(jsonb_agg(
    jsonb_strip_nulls(
      elem
      -- Fix tipo_imovel
      || CASE elem->>'tipo_imovel'
        WHEN 'comercial' THEN '{"tipo_imovel":"casa"}'::jsonb
        WHEN 'rural' THEN '{"tipo_imovel":"comercial"}'::jsonb
        ELSE '{}'::jsonb
      END
      -- Fix zona
      || CASE elem->>'zona'
        WHEN 'norte' THEN '{"zona":"sul"}'::jsonb
        WHEN 'sul' THEN '{"zona":"litoral_sudeste"}'::jsonb
        WHEN 'leste' THEN '{"zona":"sao_paulo"}'::jsonb
        ELSE '{}'::jsonb
      END
    )
  ), '[]'::jsonb)
  FROM jsonb_array_elements(a.interesses) elem
)
WHERE a.interesses IS NOT NULL
  AND a.interesses != '[]'::JSONB
  AND a.titulo_anuncio LIKE '[MOCK]%';


-- ═════════════════════════════════════════════════════════════════════
-- ETAPA 7: Enriquecer erp.clientes com dados reais dos proprietários
-- ═════════════════════════════════════════════════════════════════════
-- IMPORTANTE: Roda DEPOIS da reconstrução de mapeamento (que usa os
-- nomes "Proprietário #N" para matching). Após este UPDATE, os nomes
-- são substituídos por nomes reais.

UPDATE erp.clientes c
SET
  nome = sp.nome,
  telefone = sp.telefone,
  email = CASE
    WHEN sp.email IS NOT NULL AND sp.email != '' THEN sp.email
    ELSE c.email  -- mantém placeholder se não há email real
  END,
  observacoes = '[MIGRADO-ENRIQUECIDO] Dados reais importados na Fase 2. ID original: ' || sp.id
FROM stg_proprietario sp
WHERE c.nome = 'Proprietário #' || sp.id;


-- ═════════════════════════════════════════════════════════════════════
-- ETAPA 8: Enriquecer erp.condominios com dados reais
-- ═════════════════════════════════════════════════════════════════════

UPDATE erp.condominios c
SET
  nome = sc.nome,
  endereco = CASE
    WHEN sc.endereco IS NOT NULL THEN
      sc.endereco || CASE WHEN sc.numero > 0 THEN ', ' || sc.numero ELSE '' END
    ELSE c.endereco
  END,
  bairro = COALESCE(NULLIF(sc.bairro, ''), c.bairro),
  cidade = COALESCE(NULLIF(sc.cidade, ''), c.cidade),
  estado = COALESCE(NULLIF(sc.estado, ''), c.estado),
  cep = COALESCE(NULLIF(sc.cep, ''), c.cep),
  valor_condominio = CASE
    WHEN sc.valor_condominio > 0 THEN sc.valor_condominio
    ELSE c.valor_condominio
  END,
  observacoes = '[MIGRADO-ENRIQUECIDO] ID original: ' || sc.id
    || CASE WHEN sc.km > 0 THEN '. Km Raposo Tavares: ' || sc.km ELSE '' END
FROM stg_condominio sc
WHERE c.nome = 'Condomínio #' || sc.id;


-- ═════════════════════════════════════════════════════════════════════
-- ETAPA 9: Preencher localização dos imóveis a partir dos condominios
-- ═════════════════════════════════════════════════════════════════════
-- Na Fase 1, imóveis não tinham dados de localização (apenas FK para
-- condominio). Agora que os condominios têm dados reais, propagamos.

UPDATE erp.ativos a
SET
  cidade = c.cidade,
  bairro = c.bairro,
  estado = c.estado,
  cep = c.cep,
  logradouro = c.endereco,
  condominio_nome = c.nome
FROM erp.condominios c
WHERE a.condominio_id = c.id
  AND a.natureza = 'imovel'
  AND a.titulo_anuncio LIKE '[MOCK]%'
  AND c.cidade IS NOT NULL;

-- Também atualizar condominio_nome nos que têm condominio sem cidade
UPDATE erp.ativos a
SET condominio_nome = c.nome
FROM erp.condominios c
WHERE a.condominio_id = c.id
  AND a.natureza = 'imovel'
  AND a.titulo_anuncio LIKE '[MOCK]%'
  AND a.condominio_nome IS NULL
  AND c.nome IS NOT NULL;


-- ═════════════════════════════════════════════════════════════════════
-- ETAPA 10: Validação
-- ═════════════════════════════════════════════════════════════════════

-- 10A. Contagem de tipo_imovel corrigidos
SELECT 'TIPO_IMOVEL DISTRIBUTION' AS check_name, tipo_imovel, COUNT(*) AS total
FROM erp.ativos
WHERE titulo_anuncio LIKE '[MOCK]%' OR natureza = 'permuta_imovel'
GROUP BY tipo_imovel
ORDER BY total DESC;

-- 10B. Contagem de zona corrigidos
SELECT 'ZONA DISTRIBUTION' AS check_name, zona, COUNT(*) AS total
FROM erp.ativos
WHERE (titulo_anuncio LIKE '[MOCK]%' OR natureza = 'permuta_imovel')
  AND zona IS NOT NULL
GROUP BY zona
ORDER BY total DESC;

-- 10C. Corretores atualizados (não deve ter mais "Corretor #N")
SELECT 'REMAINING PLACEHOLDER CORRETORES' AS check_name, COUNT(*) AS total
FROM erp.ativos
WHERE corretor LIKE 'Corretor #%';
-- Expected: 0

-- 10D. Clientes enriquecidos
SELECT 'ENRICHED CLIENTES' AS check_name, COUNT(*) AS total
FROM erp.clientes
WHERE observacoes LIKE '%MIGRADO-ENRIQUECIDO%';

SELECT 'REMAINING PLACEHOLDER CLIENTES' AS check_name, COUNT(*) AS total
FROM erp.clientes
WHERE nome LIKE 'Proprietário #%';
-- Expected: 0 (ou poucos se algum proprietário não estava no lookup)

-- 10E. Condominios enriquecidos
SELECT 'ENRICHED CONDOMINIOS' AS check_name, COUNT(*) AS total
FROM erp.condominios
WHERE observacoes LIKE '%MIGRADO-ENRIQUECIDO%';

SELECT 'REMAINING PLACEHOLDER CONDOMINIOS' AS check_name, COUNT(*) AS total
FROM erp.condominios
WHERE nome LIKE 'Condomínio #%';
-- Expected: 0

-- 10F. Ativos com localização preenchida
SELECT 'ATIVOS WITH LOCATION' AS check_name, COUNT(*) AS total
FROM erp.ativos
WHERE titulo_anuncio LIKE '[MOCK]%'
  AND cidade IS NOT NULL;

-- 10G. Amostra de dados corrigidos
SELECT
  a.ref,
  a.tipo_imovel,
  a.zona,
  a.corretor,
  a.cidade,
  a.bairro,
  a.condominio_nome,
  jsonb_array_length(a.interesses) AS num_interesses
FROM erp.ativos a
WHERE a.titulo_anuncio LIKE '[MOCK]%'
  AND a.interesses != '[]'::JSONB
LIMIT 5;

-- 10H. Amostra de clientes enriquecidos
SELECT nome, telefone, email, observacoes
FROM erp.clientes
WHERE observacoes LIKE '%MIGRADO-ENRIQUECIDO%'
LIMIT 5;

-- 10I. Amostra de condominios enriquecidos
SELECT nome, cidade, bairro, cep, endereco, valor_condominio, observacoes
FROM erp.condominios
WHERE observacoes LIKE '%MIGRADO-ENRIQUECIDO%'
LIMIT 5;


COMMIT;

-- ═════════════════════════════════════════════════════════════════════
-- FIM DA FASE 2
-- ═════════════════════════════════════════════════════════════════════
