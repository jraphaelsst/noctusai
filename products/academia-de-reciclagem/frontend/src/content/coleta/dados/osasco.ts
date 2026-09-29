/**
 * Coleta domiciliar e coleta seletiva — páginas da Prefeitura de Osasco (2022-05).
 * Transcribed 2026-09-29 from the official document (names kept as the source spells them).
 * GENERATED from the transcription — edit the rows by hand when the source changes.
 */
import type { Rota } from '../tipos';

export const ROTAS: Rota[] = [
  { bairros: ["Adalgisa", "Bandeiras", "Bonança", "Cachoeirinha", "Conceição", "Conjunto Vitória", "Estrela", "Fazendinha", "Jardim Nogueira", "Jardim Roberto", "Metalúrgico", "Padroeira", "Primeiro de Maio", "Santa Maria", "São Pedro", "São Vitor"], dias: ["seg", "qua", "sex"], periodo: "diurno", tipo: 'comum' },
  { bairros: ["Bussocaba", "Campesina", "Cipava", "City Bussocaba", "Continental", "Jaguaribe", "Jardim D´Abril", "Presidente Altino", "Santo Antônio", "Veloso"], dias: ["seg", "qua", "sex"], periodo: "noturno", tipo: 'comum' },
  { bairros: ["Centro", "Vila Osasco"], dias: ["seg", "ter", "qua", "qui", "sex", "sab"], periodo: "noturno", tipo: 'comum' },
  { bairros: ["Vila Yara"], dias: ["seg", "qua", "sab"], periodo: "noturno", tipo: 'comum', nota: "Publicado assim pela prefeitura (seg/qua/sáb), diferente do padrão dos outros bairros — vale confirmar." },
  { bairros: ["Aliança", "Canaã", "Capelinha", "Helena Maria", "Jardim D´Avila", "Jardim Elvira", "Munhoz", "Portal D´Oeste", "Rochdale", "Santa Fé", "Serventina", "Vila Menck"], dias: ["ter", "qui", "sab"], periodo: "diurno", tipo: 'comum' },
  { bairros: ["Cidade das Flores", "IAPI", "Jardim das Flores", "Km 18", "Mutinga", "Piratininga", "Quitaúna", "Remédios", "Rochdale II", "Vila Ayrosa", "Vila Boralli", "Vila São José", "Vila Yolanda"], dias: ["ter", "qui", "sab"], periodo: "noturno", tipo: 'comum' },
  { bairros: ["Jd. Ayrosa", "IAPI", "Jd. Piratininga"], dias: ["seg"], tipo: 'seletiva', nota: "Inclui também: R. Antonio B. de Carvalho, R. Rita Dias Viana, R. Agemira Cerqueira, R. Alberto Euzébio da Silva" },
  { bairros: ["V. Conceição", "V. Quitaúna", "Jd. Oriental", "Jd. das Flores", "Jd. Pedro Pinho", "V. Lauci", "J. Bueno", "V. Isabel", "V. Roralli", "V. Pestana", "J. Califórnia", "J. Claudia", "KM 18", "V. Boralli", "Padroeira", "Jd. Lofredo", "Bandeiras", "Jd. Padroeira", "Jd. Roberto", "Jd. Padroeira II", "Jd. Iguaçu"], dias: ["ter"], tipo: 'seletiva' },
  { bairros: ["Bonfim", "Pres. Altino", "Jd. Rochdale"], dias: ["qua"], tipo: 'seletiva', nota: "Inclui também: R. Goiania, R. Aracaju, Av. Luiz Rink" },
  { bairros: ["Jd. Iracema", "Santo Antonio", "Jd. Das Flores", "Vila Yolanda", "V. Yolanda", "Vila Cerqueira", "Jd. Capelaro", "Jd. Brasília", "Jd. Califórnia", "Vila Quitaúna", "Jd. Mauricio", "Jd. Cacique", "Vila Iracema", "Jd. Itabaú", "Quitaúna"], dias: ["qui"], tipo: 'seletiva', nota: "Inclui também: R. José A. P. de Mendonça, R. São Francisco, Viela Jinilio da Silveira" },
  { bairros: ["Com. Anunziato", "Jd. Aliança", "Jd. Canaã", "Jd. Mutinga", "Jd. Piratininga"], dias: ["sex"], tipo: 'seletiva' },
  { bairros: ["Bussocaba City", "Jd. Novo Osasco", "Jd. D’Abril", "Vila Jaci", "Jd. Primavera", "Jd. Bussocaba", "Bussocaba", "Jd. Ype", "Jd. das Palmeiras", "S. José", "Vila Prado", "Jd. São José"], dias: ["sab"], tipo: 'seletiva', nota: "Inclui também: R. Garçia Lourenço, R. Gorga" },
];
