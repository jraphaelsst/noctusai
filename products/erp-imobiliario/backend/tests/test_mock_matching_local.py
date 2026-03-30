"""Local matching algorithm assessment. Usage: python -m tests.test_mock_matching_local"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services.matching import gerar_matches_para_imovel, _passa_filtros_minimos, calcular_compatibilidade_regiao, calcular_compatibilidade_preco, calcular_compatibilidade_specs

OA = "00000000-0000-0000-0000-000000000001"
OB = "00000000-0000-0000-0000-000000000002"
OC = "00000000-0000-0000-0000-000000000003"
_n = 0
def nid(p="x"):
    global _n; _n += 1; return f"{p}-{_n:04d}"

def imv(o,v,t,ci,es,ba,zo=None,q=None,su=None,bn=None,vg=None,ap=None,at=None,an=None,ti=None,de=None,fo=None,po=None,ob="",it=None):
    return {"id":nid("imv"),"owner_id":o,"natureza":"imovel","valor":v,"status":"ativo","aceita_permutas":True,"tipo_imovel":t,"cidade":ci,"estado":es,"bairro":ba,"zona":zo,"quartos":q,"suites":su,"banheiros":bn,"vagas":vg,"area_privativa":ap,"area_total":at,"andar":an,"titulo_anuncio":ti,"descricao_seo":de,"fotos":fo or[],"pontos_de_interesse":po,"observacoes":ob,"interesses":it or[],"finalidade":"venda"}

def pm(o,v,t,ci,es,ba=None,zo=None,fmi=None,fma=None,qm=None,vm=None,mm=None,mx=None,ac=False,rg=None,ob="",it=None):
    return {"id":nid("pm"),"owner_id":o,"natureza":"permuta_imovel","valor":v,"status":"ativo","tipo_imovel":t,"cidade":ci,"estado":es,"bairro":ba,"zona":zo,"faixa_preco_min":fmi,"faixa_preco_max":fma,"quartos_min":qm,"vagas_min":vm,"metragem_min":mm,"metragem_max":mx,"aceita_completar_diferenca":ac,"regiao_preferida":rg or[],"observacoes":ob,"interesses":it or[]}

def au(o,v,ci,es,ma=None,mo=None,tv=None,ob="",it=None):
    return {"id":nid("au"),"owner_id":o,"natureza":"permuta_automovel","valor":v,"status":"ativo","cidade":ci,"estado":es,"marca":ma,"modelo":mo,"tipo_veiculo":tv,"observacoes":ob,"interesses":it or[]}

# 100 imóveis (same as before)
I=[
    imv(OA,450000,"apartamento","São Paulo","SP","Moema","Zona Sul",2,1,2,1,65,72,8,"Apto Moema","R",["f1","f2","f3"],["M"],"SP-ZS-01",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":300000,"valor_max":600000}]),
    imv(OA,680000,"apartamento","São Paulo","SP","Vila Mariana","Zona Sul",3,1,2,2,85,95,12,"Apto VM","A",["f1","f2","f3","f4"],["M"],"SP-ZS-02",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":400000,"valor_max":800000}]),
    imv(OA,520000,"apartamento","São Paulo","SP","Saúde","Zona Sul",2,1,1,1,58,64,5,"Apto Saúde","2",["f1","f2"],["M"],"SP-ZS-03",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":350000,"valor_max":700000}]),
    imv(OC,950000,"apartamento","São Paulo","SP","Brooklin","Zona Sul",3,2,3,2,110,125,18,"Apto Brooklin","AP",["f1","f2","f3","f4","f5"],["S"],"SP-ZS-04",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":600000,"valor_max":1200000},{"tipo":"automovel","marca":"BMW","valor_min":150000,"valor_max":300000}]),
    imv(OA,380000,"apartamento","São Paulo","SP","Jabaquara","Zona Sul",2,0,1,1,50,55,3,"Apto Jab","E",["f1","f2"],["M"],"SP-ZS-05",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":250000,"valor_max":500000}]),
    imv(OA,1150000,"casa","São Paulo","SP","Campo Belo","Zona Sul",4,2,4,3,180,220,None,"Casa CB","S",["f1","f2","f3","f4","f5","f6"],["S"],"SP-ZS-06",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"São Paulo","valor_min":800000,"valor_max":1500000}]),
    imv(OC,420000,"apartamento","São Paulo","SP","Santo Amaro","Zona Sul",2,1,1,1,55,60,6,"Apto SA","M",["f1","f2","f3"],["M"],"SP-ZS-07",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":300000,"valor_max":550000}]),
    imv(OA,780000,"apartamento","São Paulo","SP","Moema","Zona Sul",3,1,2,2,92,105,15,"Apto Moema3","R",["f1","f2","f3","f4"],["I"],"SP-ZS-08",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":500000,"valor_max":1000000}]),
    imv(OA,550000,"apartamento","São Paulo","SP","Chácara Klabin","Zona Sul",2,1,2,1,70,78,10,"Apto CK","V",["f1","f2","f3"],["A"],"SP-ZS-09",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":350000,"valor_max":700000}]),
    imv(OC,890000,"cobertura","São Paulo","SP","Vila Mariana","Zona Sul",3,2,3,2,140,180,20,"Cob VM","D",["f1","f2","f3","f4","f5"],["M"],"SP-ZS-10",[{"tipo":"imovel","tipo_imovel":"cobertura","cidade":"São Paulo","valor_min":600000,"valor_max":1200000}]),
    imv(OA,470000,"apartamento","São Paulo","SP","Sacomã","Zona Sul",2,1,1,1,52,58,7,"Apto Sac","N",["f1","f2"],["M"],"SP-ZS-11",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":300000,"valor_max":600000}]),
    imv(OA,620000,"apartamento","São Paulo","SP","Ipiranga","Zona Sul",3,1,2,1,78,88,9,"Apto Ip","3",["f1","f2","f3"],["M"],"SP-ZS-12",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":400000,"valor_max":800000}]),
    imv(OC,350000,"studio","São Paulo","SP","Vila Clementino","Zona Sul",1,0,1,1,35,38,14,"Studio VC","C",["f1","f2"],["U"],"SP-ZS-13",[{"tipo":"imovel","tipo_imovel":"studio","cidade":"São Paulo","valor_min":200000,"valor_max":450000}]),
    imv(OA,1050000,"apartamento","São Paulo","SP","Itaim Bibi","Zona Sul",3,2,3,2,120,135,22,"Apto Itaim","AP",["f1","f2","f3","f4","f5"],["F"],"SP-ZS-14",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":700000,"valor_max":1400000}]),
    imv(OA,490000,"apartamento","São Paulo","SP","Cursino","Zona Sul",2,1,1,1,56,62,4,"Apto Cur","R",["f1","f2"],None,"SP-ZS-15",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":300000,"valor_max":650000}]),
    imv(OC,720000,"apartamento","São Paulo","SP","Saúde","Zona Sul",3,1,2,2,88,98,11,"Apto S3","E",["f1","f2","f3","f4"],["M"],"SP-ZS-16",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":500000,"valor_max":900000}]),
    imv(OA,1200000,"casa","São Paulo","SP","Granja Julieta","Zona Sul",4,3,5,4,250,350,None,"Casa GJ","4",["f1","f2","f3","f4","f5","f6","f7"],["S"],"SP-ZS-17",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"São Paulo","valor_min":900000,"valor_max":1800000},{"tipo":"automovel","marca":"Mercedes-Benz","valor_min":200000,"valor_max":500000}]),
    imv(OA,580000,"apartamento","São Paulo","SP","Brooklin","Zona Sul",2,1,2,1,68,75,16,"Apto Br2","M",["f1","f2","f3"],["B"],"SP-ZS-18",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":400000,"valor_max":750000}]),
    imv(OC,410000,"apartamento","São Paulo","SP","Vila Mascote","Zona Sul",2,0,1,1,48,54,2,"Apto VM2","T",["f1","f2"],None,"SP-ZS-19",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":250000,"valor_max":550000}]),
    imv(OA,830000,"apartamento","São Paulo","SP","Campo Belo","Zona Sul",3,1,2,2,95,108,13,"Apto CB","A",["f1","f2","f3","f4"],["C"],"SP-ZS-20",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":550000,"valor_max":1100000}]),
    # ZO 15
    imv(OA,550000,"apartamento","São Paulo","SP","Pinheiros","Zona Oeste",2,1,1,1,60,68,7,"Apto P","C",["f1","f2","f3"],["M"],"SP-ZO-01",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":350000,"valor_max":700000}]),
    imv(OC,920000,"apartamento","São Paulo","SP","Vila Madalena","Zona Oeste",3,1,2,2,95,108,10,"Apto VM","R",["f1","f2","f3","f4"],["B"],"SP-ZO-02",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":600000,"valor_max":1200000}]),
    imv(OA,750000,"apartamento","São Paulo","SP","Perdizes","Zona Oeste",3,1,2,1,82,92,8,"Apto Per","S",["f1","f2","f3"],["P"],"SP-ZO-03",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":500000,"valor_max":1000000}]),
    imv(OA,1350000,"casa","São Paulo","SP","Alto de Pinheiros","Zona Oeste",4,2,4,3,200,300,None,"Casa AP","S",["f1","f2","f3","f4","f5"],["V"],"SP-ZO-04",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"São Paulo","valor_min":1000000,"valor_max":2000000}]),
    imv(OC,480000,"apartamento","São Paulo","SP","Lapa","Zona Oeste",2,0,1,1,52,58,4,"Apto L","E",["f1","f2"],["E"],"SP-ZO-05",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":300000,"valor_max":600000}]),
    imv(OA,650000,"apartamento","São Paulo","SP","Pompeia","Zona Oeste",2,1,2,1,72,80,11,"Apto Pom","M",["f1","f2","f3"],["S"],"SP-ZO-06",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":450000,"valor_max":850000}]),
    imv(OA,1100000,"apartamento","São Paulo","SP","Pinheiros","Zona Oeste",3,2,3,2,115,130,19,"Apto PAP","3",["f1","f2","f3","f4","f5"],["M"],"SP-ZO-07",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":750000,"valor_max":1500000}]),
    imv(OC,530000,"apartamento","São Paulo","SP","Barra Funda","Zona Oeste",2,1,1,1,58,65,6,"Apto BF","M",["f1","f2"],["M"],"SP-ZO-08",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":350000,"valor_max":700000}]),
    imv(OA,870000,"apartamento","São Paulo","SP","Sumaré","Zona Oeste",3,1,2,2,90,100,14,"Apto Sum","V",["f1","f2","f3","f4"],["P"],"SP-ZO-09",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":600000,"valor_max":1100000}]),
    imv(OA,440000,"studio","São Paulo","SP","Vila Leopoldina","Zona Oeste",1,0,1,1,38,42,20,"Studio VL","N",["f1","f2"],["V"],"SP-ZO-10",[{"tipo":"imovel","tipo_imovel":"studio","cidade":"São Paulo","valor_min":250000,"valor_max":550000}]),
    imv(OC,680000,"apartamento","São Paulo","SP","Água Branca","Zona Oeste",3,1,2,1,80,90,9,"Apto AB","3",["f1","f2","f3"],["P"],"SP-ZO-11",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":450000,"valor_max":900000}]),
    imv(OA,990000,"cobertura","São Paulo","SP","Perdizes","Zona Oeste",3,2,3,2,150,200,18,"Cob Per","T",["f1","f2","f3","f4","f5"],["P"],"SP-ZO-12",[{"tipo":"imovel","tipo_imovel":"cobertura","cidade":"São Paulo","valor_min":700000,"valor_max":1300000}]),
    imv(OA,510000,"apartamento","São Paulo","SP","Butantã","Zona Oeste",2,1,1,1,55,62,5,"Apto But","U",["f1","f2"],["U"],"SP-ZO-13",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":350000,"valor_max":650000}]),
    imv(OC,1500000,"casa","São Paulo","SP","City Boaçava","Zona Oeste",5,3,5,4,280,400,None,"Casa CB","L",["f1","f2","f3","f4","f5","f6"],["V"],"SP-ZO-14",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"São Paulo","valor_min":1000000,"valor_max":2500000},{"tipo":"automovel","marca":"Porsche","valor_min":300000,"valor_max":800000}]),
    imv(OA,600000,"apartamento","São Paulo","SP","Vila Romana","Zona Oeste",2,1,2,1,65,72,8,"Apto VR","2",["f1","f2","f3"],None,"SP-ZO-15",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":400000,"valor_max":800000}]),
    # ZN/ZL 15
    imv(OA,320000,"apartamento","São Paulo","SP","Santana","Zona Norte",2,0,1,1,48,52,3,"Apto San","M",["f1","f2"],["M"],"SP-ZN-01",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":200000,"valor_max":450000}]),
    imv(OC,450000,"apartamento","São Paulo","SP","Tucuruvi","Zona Norte",2,1,2,1,60,68,8,"Apto Tuc","N",["f1","f2","f3"],["M"],"SP-ZN-02",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":300000,"valor_max":600000}]),
    imv(OA,580000,"apartamento","São Paulo","SP","Mandaqui","Zona Norte",3,1,2,1,75,85,6,"Apto Man","F",["f1","f2","f3"],["H"],"SP-ZN-03",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":400000,"valor_max":750000}]),
    imv(OA,280000,"apartamento","São Paulo","SP","Vila Maria","Zona Norte",2,0,1,1,45,48,2,"Apto VM","E",["f1"],None,"SP-ZN-04",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":180000,"valor_max":380000}]),
    imv(OC,750000,"casa","São Paulo","SP","Tremembé","Zona Norte",3,1,3,2,130,200,None,"Casa Tr","Q",["f1","f2","f3"],["H"],"SP-ZN-05",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"São Paulo","valor_min":500000,"valor_max":1000000}]),
    imv(OA,380000,"apartamento","São Paulo","SP","Tatuapé","Zona Leste",2,1,1,1,55,60,5,"Apto Tat","M",["f1","f2"],["M"],"SP-ZL-01",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":250000,"valor_max":500000}]),
    imv(OA,520000,"apartamento","São Paulo","SP","Anália Franco","Zona Leste",3,1,2,1,72,82,10,"Apto AF","V",["f1","f2","f3"],["S"],"SP-ZL-02",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":350000,"valor_max":700000}]),
    imv(OC,290000,"apartamento","São Paulo","SP","Penha","Zona Leste",2,0,1,1,46,50,3,"Apto Pen","B",["f1"],["M"],"SP-ZL-03",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":180000,"valor_max":400000}]),
    imv(OA,650000,"apartamento","São Paulo","SP","Mooca","Zona Leste",3,1,2,2,85,95,12,"Apto Moo","T",["f1","f2","f3","f4"],["S"],"SP-ZL-04",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":450000,"valor_max":850000}]),
    imv(OA,420000,"apartamento","São Paulo","SP","Vila Formosa","Zona Leste",2,1,1,1,54,60,6,"Apto VF","P",["f1","f2"],["C"],"SP-ZL-05",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":280000,"valor_max":550000}]),
    imv(OC,800000,"casa","São Paulo","SP","Tatuapé","Zona Leste",3,2,3,2,150,200,None,"Casa Tat","S",["f1","f2","f3","f4","f5"],["S"],"SP-ZL-06",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"São Paulo","valor_min":550000,"valor_max":1100000}]),
    imv(OA,350000,"apartamento","São Paulo","SP","Belém","Zona Leste",2,0,1,1,50,55,4,"Apto Bel","V",["f1","f2"],["M"],"SP-ZL-07",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":220000,"valor_max":480000}]),
    imv(OA,470000,"apartamento","São Paulo","SP","Vila Prudente","Zona Leste",2,1,2,1,62,70,9,"Apto VP","N",["f1","f2","f3"],["M"],"SP-ZL-08",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":300000,"valor_max":600000}]),
    imv(OC,560000,"apartamento","São Paulo","SP","Carrão","Zona Leste",3,1,2,1,76,86,7,"Apto Car","F",["f1","f2","f3"],["M"],"SP-ZL-09",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":380000,"valor_max":720000}]),
    imv(OA,700000,"apartamento","São Paulo","SP","Jardim Anália Franco","Zona Leste",3,2,3,2,100,115,16,"Apto JAF","AP",["f1","f2","f3","f4","f5"],["S"],"SP-ZL-10",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":500000,"valor_max":900000}]),
    # ABC 15
    imv(OA,350000,"apartamento","Santo André","SP","Centro",None,2,1,1,1,55,62,5,"Apto SA","C",["f1","f2"],["S"],"ABC-01",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Santo André","valor_min":220000,"valor_max":480000}]),
    imv(OC,480000,"apartamento","São Bernardo do Campo","SP","Centro",None,3,1,2,1,72,80,8,"Apto SBC","C",["f1","f2","f3"],["G"],"ABC-02",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Bernardo do Campo","valor_min":320000,"valor_max":620000}]),
    imv(OA,420000,"apartamento","São Caetano do Sul","SP","Santa Paula",None,2,1,2,1,65,72,10,"Apto SCS","I",["f1","f2","f3"],["P"],"ABC-03",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Caetano do Sul","valor_min":280000,"valor_max":550000}]),
    imv(OA,580000,"apartamento","Santo André","SP","Jardim",None,3,1,2,2,85,95,12,"Apto JSA","2",["f1","f2","f3","f4"],None,"ABC-04",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Santo André","valor_min":400000,"valor_max":750000}]),
    imv(OC,300000,"apartamento","Diadema","SP","Centro",None,2,0,1,1,48,52,3,"Apto Dia","E",["f1","f2"],None,"ABC-05",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Diadema","valor_min":180000,"valor_max":400000}]),
    imv(OA,650000,"casa","São Bernardo do Campo","SP","Rudge Ramos",None,3,1,3,2,140,200,None,"Casa SBC","C",["f1","f2","f3","f4"],None,"ABC-06",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"São Bernardo do Campo","valor_min":450000,"valor_max":850000}]),
    imv(OA,380000,"apartamento","Mauá","SP","Centro",None,2,0,1,1,50,56,4,"Apto Mauá","C",["f1","f2"],None,"ABC-07",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Mauá","valor_min":240000,"valor_max":500000}]),
    imv(OC,520000,"apartamento","São Caetano do Sul","SP","Osvaldo Cruz",None,3,1,2,1,78,88,9,"Apto OC","N",["f1","f2","f3"],["S"],"ABC-08",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Caetano do Sul","valor_min":350000,"valor_max":680000}]),
    imv(OA,700000,"cobertura","Santo André","SP","Campestre",None,3,2,3,2,130,170,15,"Cob SA","D",["f1","f2","f3","f4","f5"],None,"ABC-09",[{"tipo":"imovel","tipo_imovel":"cobertura","cidade":"Santo André","valor_min":500000,"valor_max":900000}]),
    imv(OA,260000,"apartamento","Ribeirão Pires","SP","Centro",None,2,0,1,1,45,48,2,"Apto RP","T",["f1"],None,"ABC-10",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Ribeirão Pires","valor_min":160000,"valor_max":350000}]),
    imv(OC,450000,"apartamento","São Bernardo do Campo","SP","Baeta Neves",None,2,1,2,1,62,70,7,"Apto BN","2",["f1","f2","f3"],None,"ABC-11",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Bernardo do Campo","valor_min":300000,"valor_max":580000}]),
    imv(OA,550000,"apartamento","São Caetano do Sul","SP","Barcelona",None,3,1,2,2,82,92,11,"Apto Bar","A",["f1","f2","f3","f4"],["S"],"ABC-12",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Caetano do Sul","valor_min":380000,"valor_max":720000}]),
    imv(OA,320000,"apartamento","Santo André","SP","Vila Assunção",None,2,0,1,1,50,55,4,"Apto VA","2",["f1","f2"],None,"ABC-13",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Santo André","valor_min":200000,"valor_max":430000}]),
    imv(OC,680000,"casa","São Caetano do Sul","SP","Olímpico",None,3,2,3,2,160,220,None,"Casa SCS","3",["f1","f2","f3","f4"],["E"],"ABC-14",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"São Caetano do Sul","valor_min":480000,"valor_max":880000}]),
    imv(OA,400000,"apartamento","São Bernardo do Campo","SP","Nova Petrópolis",None,2,1,1,1,58,65,6,"Apto NP","2",["f1","f2"],["S"],"ABC-15",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Bernardo do Campo","valor_min":260000,"valor_max":530000}]),
    # CPS 15
    imv(OA,380000,"apartamento","Campinas","SP","Cambuí",None,2,1,1,1,58,65,7,"Apto Cam","N",["f1","f2","f3"],["S"],"CPS-01",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Campinas","valor_min":250000,"valor_max":500000}]),
    imv(OC,550000,"apartamento","Campinas","SP","Taquaral",None,3,1,2,2,80,90,10,"Apto Taq","L",["f1","f2","f3","f4"],["L"],"CPS-02",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Campinas","valor_min":380000,"valor_max":720000}]),
    imv(OA,450000,"apartamento","Campinas","SP","Barão Geraldo",None,2,1,2,1,65,72,8,"Apto BG","U",["f1","f2","f3"],["U"],"CPS-03",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Campinas","valor_min":300000,"valor_max":600000}]),
    imv(OA,780000,"casa","Campinas","SP","Sousas",None,4,2,3,3,180,300,None,"Casa Sou","N",["f1","f2","f3","f4","f5"],None,"CPS-04",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"Campinas","valor_min":550000,"valor_max":1000000}]),
    imv(OC,320000,"apartamento","Campinas","SP","Centro",None,2,0,1,1,50,55,4,"Apto CtrCPS","C",["f1","f2"],None,"CPS-05",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Campinas","valor_min":200000,"valor_max":430000}]),
    imv(OA,650000,"apartamento","Campinas","SP","Nova Campinas",None,3,1,2,2,88,100,14,"Apto NC","N",["f1","f2","f3","f4"],["I"],"CPS-06",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Campinas","valor_min":450000,"valor_max":850000}]),
    imv(OA,280000,"apartamento","Campinas","SP","Jardim Chapadão",None,2,0,1,1,46,50,2,"Apto Chap","E",["f1"],None,"CPS-07",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Campinas","valor_min":180000,"valor_max":380000}]),
    imv(OC,900000,"casa","Campinas","SP","Gramado",None,4,2,4,3,200,350,None,"Casa Gram","C",["f1","f2","f3","f4","f5","f6"],None,"CPS-08",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"Campinas","valor_min":650000,"valor_max":1200000}]),
    imv(OA,420000,"apartamento","Valinhos","SP","Centro",None,2,1,2,1,62,70,6,"Apto Val","T",["f1","f2","f3"],None,"CPS-09",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Valinhos","valor_min":280000,"valor_max":560000}]),
    imv(OA,500000,"apartamento","Campinas","SP","Alphaville",None,3,1,2,2,82,92,11,"Apto Alpha","S",["f1","f2","f3"],None,"CPS-10",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Campinas","valor_min":340000,"valor_max":660000}]),
    imv(OC,350000,"apartamento","Sumaré","SP","Centro",None,2,0,1,1,52,58,3,"Apto Sum","P",["f1","f2"],None,"CPS-11",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Sumaré","valor_min":220000,"valor_max":470000}]),
    imv(OA,580000,"apartamento","Campinas","SP","Swift",None,3,1,2,1,75,85,9,"Apto Swi","R",["f1","f2","f3"],None,"CPS-12",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Campinas","valor_min":400000,"valor_max":760000}]),
    imv(OA,700000,"cobertura","Campinas","SP","Cambuí",None,3,2,3,2,140,180,18,"Cob Cam","P",["f1","f2","f3","f4","f5"],["C"],"CPS-13",[{"tipo":"imovel","tipo_imovel":"cobertura","cidade":"Campinas","valor_min":500000,"valor_max":920000}]),
    imv(OC,480000,"apartamento","Indaiatuba","SP","Centro",None,3,1,2,1,72,80,7,"Apto Ind","Q",["f1","f2","f3"],None,"CPS-14",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Indaiatuba","valor_min":320000,"valor_max":630000}]),
    imv(OA,620000,"casa","Vinhedo","SP","Centro",None,3,1,3,2,150,250,None,"Casa Vin","Q",["f1","f2","f3","f4"],None,"CPS-15",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"Vinhedo","valor_min":420000,"valor_max":820000}]),
    # LIT 10
    imv(OA,450000,"apartamento","Santos","SP","Gonzaga",None,2,1,1,1,60,68,8,"Apto Gon","P",["f1","f2","f3"],["P"],"LIT-01",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Santos","valor_min":300000,"valor_max":600000}]),
    imv(OC,650000,"apartamento","Santos","SP","Ponta da Praia",None,3,1,2,1,85,95,12,"Apto PP","V",["f1","f2","f3","f4"],["A"],"LIT-02",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Santos","valor_min":450000,"valor_max":850000}]),
    imv(OA,380000,"apartamento","Guarujá","SP","Pitangueiras",None,2,1,1,1,55,62,6,"Apto Pit","P",["f1","f2"],["P"],"LIT-03",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Guarujá","valor_min":250000,"valor_max":500000}]),
    imv(OA,900000,"cobertura","Santos","SP","Boqueirão",None,3,2,3,2,150,200,20,"Cob Boq","F",["f1","f2","f3","f4","f5"],["P"],"LIT-04",[{"tipo":"imovel","tipo_imovel":"cobertura","cidade":"Santos","valor_min":650000,"valor_max":1200000}]),
    imv(OC,320000,"apartamento","Praia Grande","SP","Boqueirão",None,2,0,1,1,50,55,4,"Apto PG","P",["f1","f2"],["P"],"LIT-05",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Praia Grande","valor_min":200000,"valor_max":430000}]),
    imv(OA,520000,"apartamento","Santos","SP","Embaré",None,3,1,2,1,78,88,10,"Apto Emb","1",["f1","f2","f3"],["P"],"LIT-06",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Santos","valor_min":350000,"valor_max":680000}]),
    imv(OA,750000,"casa","Bertioga","SP","Riviera de São Lourenço",None,4,2,4,3,180,280,None,"Casa Riv","P",["f1","f2","f3","f4","f5"],["P"],"LIT-07",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"Bertioga","valor_min":530000,"valor_max":1000000}]),
    imv(OC,420000,"apartamento","São Vicente","SP","Itararé",None,2,1,1,1,58,65,7,"Apto SV","V",["f1","f2"],["P"],"LIT-08",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Vicente","valor_min":280000,"valor_max":560000}]),
    imv(OA,580000,"apartamento","Guarujá","SP","Enseada",None,3,1,2,2,82,92,9,"Apto Ens","P",["f1","f2","f3"],["P"],"LIT-09",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Guarujá","valor_min":400000,"valor_max":760000}]),
    imv(OA,300000,"apartamento","Mongaguá","SP","Centro",None,2,0,1,1,48,52,3,"Apto Mon","P",["f1","f2"],["P"],"LIT-10",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Mongaguá","valor_min":180000,"valor_max":400000}]),
    # CWB/INT 10
    imv(OC,420000,"apartamento","Curitiba","PR","Batel",None,2,1,2,1,65,72,10,"Apto Bat","N",["f1","f2","f3"],["S"],"CWB-01",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Curitiba","valor_min":280000,"valor_max":560000}]),
    imv(OA,580000,"apartamento","Curitiba","PR","Água Verde",None,3,1,2,2,82,92,12,"Apto AV","N",["f1","f2","f3","f4"],["P"],"CWB-02",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Curitiba","valor_min":400000,"valor_max":760000}]),
    imv(OA,350000,"apartamento","Curitiba","PR","Centro Cívico",None,2,0,1,1,52,58,5,"Apto CC","C",["f1","f2"],["M"],"CWB-03",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Curitiba","valor_min":220000,"valor_max":470000}]),
    imv(OC,750000,"casa","Curitiba","PR","Santa Felicidade",None,4,2,3,3,180,280,None,"Casa SF","I",["f1","f2","f3","f4","f5"],None,"CWB-04",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"Curitiba","valor_min":520000,"valor_max":1000000}]),
    imv(OA,480000,"apartamento","Sorocaba","SP","Campolim",None,3,1,2,1,75,85,8,"Apto Cam","N",["f1","f2","f3"],None,"INT-01",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Sorocaba","valor_min":320000,"valor_max":630000}]),
    imv(OA,380000,"apartamento","Jundiaí","SP","Centro",None,2,1,1,1,58,65,6,"Apto Jun","C",["f1","f2"],None,"INT-02",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Jundiaí","valor_min":250000,"valor_max":500000}]),
    imv(OC,550000,"apartamento","Ribeirão Preto","SP","Jardim Botânico",None,3,1,2,2,85,95,10,"Apto RP","3",["f1","f2","f3"],None,"INT-03",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Ribeirão Preto","valor_min":380000,"valor_max":720000}]),
    imv(OA,800000,"casa","São José dos Campos","SP","Jardim Aquarius",None,4,2,4,3,200,300,None,"Casa Aq","AP",["f1","f2","f3","f4","f5"],None,"INT-04",[{"tipo":"imovel","tipo_imovel":"casa","cidade":"São José dos Campos","valor_min":550000,"valor_max":1050000}]),
    imv(OA,300000,"apartamento","Piracicaba","SP","Centro",None,2,0,1,1,50,55,4,"Apto Pir","C",["f1","f2"],None,"INT-05",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Piracicaba","valor_min":190000,"valor_max":400000}]),
    imv(OC,650000,"apartamento","São José dos Campos","SP","Vila Adyana",None,3,1,2,2,88,100,14,"Apto VA","N",["f1","f2","f3","f4"],None,"INT-06",[{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São José dos Campos","valor_min":450000,"valor_max":850000}]),
]

P=[
    # HIGH — well-defined interesses, same region as their offering
    pm(OB,430000,"apartamento","São Paulo","SP","Moema","Zona Sul",380000,520000,2,1,50,80,True,["Moema","Vila Mariana"],"PERM-HIGH-01",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":350000,"valor_max":550000}]),
    pm(OB,700000,"apartamento","São Paulo","SP","Vila Mariana","Zona Sul",600000,800000,3,1,75,120,True,["Vila Mariana","Moema","Saúde"],"PERM-HIGH-02",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":500000,"valor_max":900000}]),
    pm(OB,900000,"apartamento","São Paulo","SP","Brooklin","Zona Sul",800000,1100000,3,2,90,140,True,["Brooklin","Itaim Bibi"],"PERM-HIGH-03",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":800000,"valor_max":1200000}]),
    pm(OB,500000,"apartamento","São Paulo","SP","Pinheiros","Zona Oeste",450000,650000,2,1,55,75,True,["Pinheiros","Vila Madalena"],"PERM-HIGH-04",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":400000,"valor_max":700000}]),
    pm(OB,1100000,"casa","São Paulo","SP","Campo Belo","Zona Sul",900000,1300000,4,2,160,280,True,["Campo Belo","Granja Julieta"],"PERM-HIGH-05",
       [{"tipo":"imovel","tipo_imovel":"casa","cidade":"São Paulo","valor_min":900000,"valor_max":1500000}]),
    pm(OB,350000,"apartamento","Santo André","SP","Centro",None,280000,420000,2,1,45,70,True,["Santo André","São Bernardo"],"PERM-HIGH-06",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Santo André","valor_min":250000,"valor_max":450000}]),
    pm(OB,550000,"apartamento","Campinas","SP","Taquaral",None,450000,650000,3,1,70,100,True,["Taquaral","Cambuí"],"PERM-HIGH-07",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Campinas","valor_min":400000,"valor_max":700000}]),
    pm(OB,450000,"apartamento","Santos","SP","Gonzaga",None,380000,550000,2,1,50,75,True,["Gonzaga","Boqueirão"],"PERM-HIGH-08",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Santos","valor_min":350000,"valor_max":600000}]),
    pm(OB,580000,"apartamento","Curitiba","PR","Água Verde",None,480000,680000,3,1,70,100,True,["Água Verde","Batel"],"PERM-HIGH-09",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Curitiba","valor_min":400000,"valor_max":700000}]),
    pm(OB,1000000,"apartamento","São Paulo","SP","Itaim Bibi","Zona Sul",850000,1200000,3,2,100,150,True,["Itaim Bibi","Pinheiros","Brooklin"],"PERM-HIGH-10",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":800000,"valor_max":1400000}]),
    # MED — broader interesses, some cross-city, some open tipo_imovel
    pm(OB,600000,"apartamento","São Paulo","SP","Liberdade","Zona Sul",400000,750000,2,1,50,90,False,["Liberdade","Aclimação","Vila Mariana"],"PERM-MED-01",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":400000,"valor_max":800000}]),
    pm(OB,400000,"apartamento","São Paulo","SP","Consolação","Zona Oeste",300000,550000,2,0,40,70,False,["Consolação","Higienópolis","Perdizes"],"PERM-MED-02",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":300000,"valor_max":600000}]),
    pm(OB,750000,"casa","São Paulo","SP","Planalto Paulista","Zona Sul",550000,900000,3,1,100,200,False,["Planalto Paulista","Moema","Saúde"],"PERM-MED-03",
       [{"tipo":"imovel","tipo_imovel":"casa","cidade":"São Paulo","valor_min":600000,"valor_max":1000000}]),
    pm(OB,500000,"apartamento","São Paulo","SP","Cambuci",None,350000,620000,2,1,50,80,True,["Cambuci","Ipiranga","Sacomã"],"PERM-MED-04",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":300000,"valor_max":650000}]),
    pm(OB,800000,"apartamento","São Paulo","SP","Jardins","Zona Oeste",600000,1000000,3,1,80,130,False,["Jardins","Pinheiros","Itaim"],"PERM-MED-05",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":600000,"valor_max":1100000}]),
    pm(OB,450000,"apartamento","São Bernardo do Campo","SP","Planalto",None,320000,580000,2,1,55,80,True,["São Bernardo","Santo André"],"PERM-MED-06",
       [{"tipo":"imovel","cidade":"São Bernardo do Campo","valor_min":300000,"valor_max":600000}]),
    pm(OB,380000,"apartamento","Campinas","SP","Jardim Proença",None,250000,500000,2,0,40,70,False,["Campinas"],"PERM-MED-07",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Campinas","valor_min":250000,"valor_max":550000}]),
    pm(OB,650000,"casa","Campinas","SP","Taquaral",None,500000,850000,3,2,120,250,True,["Campinas","Valinhos"],"PERM-MED-08",
       [{"tipo":"imovel","cidade":"Campinas","valor_min":450000,"valor_max":900000}]),
    pm(OB,350000,"apartamento","Santos","SP","José Menino",None,250000,480000,2,0,45,70,False,["Santos","São Vicente"],"PERM-MED-09",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Santos","valor_min":250000,"valor_max":500000}]),
    pm(OB,500000,"apartamento","Curitiba","PR","Portão",None,380000,650000,2,1,55,85,True,["Curitiba"],"PERM-MED-10",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Curitiba","valor_min":350000,"valor_max":650000}]),
    # LOW — out-of-state, no overlap with imovel pool
    pm(OB,500000,"apartamento","Rio de Janeiro","RJ","Copacabana",None,350000,700000,2,0,40,80,False,["Rio de Janeiro"],"PERM-LOW-01",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Rio de Janeiro","valor_min":300000,"valor_max":700000}]),
    pm(OB,800000,"casa","Belo Horizonte","MG","Savassi",None,550000,1000000,3,1,100,250,False,["Belo Horizonte"],"PERM-LOW-02",
       [{"tipo":"imovel","tipo_imovel":"casa","cidade":"Belo Horizonte","valor_min":500000,"valor_max":1000000}]),
    pm(OB,300000,"apartamento","Florianópolis","SC","Centro",None,200000,450000,2,0,40,65,False,["Florianópolis"],"PERM-LOW-03",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Florianópolis","valor_min":200000,"valor_max":500000}]),
    pm(OB,600000,"apartamento","Porto Alegre","RS","Moinhos de Vento",None,450000,800000,3,1,70,110,False,["Porto Alegre"],"PERM-LOW-04",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Porto Alegre","valor_min":400000,"valor_max":800000}]),
    pm(OB,400000,"apartamento","Recife","PE","Boa Viagem",None,280000,550000,2,1,50,75,True,["Recife"],"PERM-LOW-05",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Recife","valor_min":250000,"valor_max":550000}]),
]
PA=[
    # AUTO — each wants a specific type of imóvel in SP
    au(OB,250000,"São Paulo","SP","BMW","X3","suv","PERM-AUTO-01",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":400000,"valor_max":800000}]),
    au(OB,180000,"São Paulo","SP","Mercedes-Benz","C200","sedan","PERM-AUTO-02",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":600000,"valor_max":1200000}]),
    au(OB,350000,"São Paulo","SP","Porsche","Macan","suv","PERM-AUTO-03",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"São Paulo","valor_min":800000,"valor_max":1500000}]),
    au(OB,500000,"São Paulo","SP","Porsche","Cayenne","suv","PERM-AUTO-04",
       [{"tipo":"imovel","tipo_imovel":"casa","cidade":"São Paulo","valor_min":1000000,"valor_max":2000000}]),
    au(OB,120000,"Campinas","SP","Toyota","Corolla Cross","hatch","PERM-AUTO-05",
       [{"tipo":"imovel","tipo_imovel":"apartamento","cidade":"Campinas","valor_min":300000,"valor_max":600000}]),
]
ALL=P+PA

def run():
    print("="*80)
    print("MATCHING ASSESSMENT — WITH BILATERAL LOGIC")
    print(f"Imóveis: {len(I)} | Permutas: {len(ALL)} (imovel: {len(P)}, auto: {len(PA)})")
    print("="*80)

    # Quick bilateral verification
    print("\n── Bilateral Filter Verification ──")
    only_auto = [x for x in I if x["interesses"] and all(i.get("tipo")=="automovel" for i in x["interesses"])]
    both = [x for x in I if x["interesses"] and len({i.get("tipo") for i in x["interesses"]}) > 1]
    only_imov = [x for x in I if x["interesses"] and all(i.get("tipo")=="imovel" for i in x["interesses"])]
    no_int = [x for x in I if not x["interesses"]]
    print(f"  Only-imovel interest: {len(only_imov)} (should only match permuta_imovel)")
    print(f"  Only-auto interest:   {len(only_auto)} (should only match permuta_automovel)")
    print(f"  Both types:           {len(both)} (can match either)")
    print(f"  No interesses:        {len(no_int)} (open to all)")

    all_m=[]
    for im in I:
        all_m.extend(gerar_matches_para_imovel(im, ALL))

    print(f"\nTotal matches: {len(all_m)}")
    possible = len(I)*len(ALL)
    print(f"Possible pairs: {possible} | Match rate: {len(all_m)/possible*100:.1f}%")
    if not all_m: print("NO MATCHES"); return

    scores=[m["score"] for m in all_m]
    print(f"Score range: {min(scores):.0f}–{max(scores):.0f} | Avg: {sum(scores)/len(scores):.1f}")

    bk={"90+":0,"80-89":0,"70-79":0,"60-69":0,"50-59":0,"45-49":0}
    for s in scores:
        if s>=90:bk["90+"]+=1
        elif s>=80:bk["80-89"]+=1
        elif s>=70:bk["70-79"]+=1
        elif s>=60:bk["60-69"]+=1
        elif s>=50:bk["50-59"]+=1
        else:bk["45-49"]+=1
    print("\n── Score Distribution ──")
    for b,c in bk.items():
        bar="█"*max(1,c//3) if c>0 else ""
        print(f"  {b:6s}: {c:4d}  {bar}")

    print("\n── Matches by Group ──")
    gr={"HIGH":[],"MED":[],"LOW":[],"AUTO":[]}
    for m in all_m:
        ob=next((p["observacoes"] for p in ALL if p["id"]==m["ativo_destino_id"]),"")
        if "HIGH" in ob:gr["HIGH"].append(m)
        elif "MED" in ob:gr["MED"].append(m)
        elif "LOW" in ob:gr["LOW"].append(m)
        elif "AUTO" in ob:gr["AUTO"].append(m)
    for g,ms in gr.items():
        if ms:
            gs=[m["score"] for m in ms]
            print(f"  {g:5s}: {len(ms):4d} matches | avg {sum(gs)/len(gs):5.1f} | range {min(gs):.0f}-{max(gs):.0f}")
        else:
            print(f"  {g:5s}:    0 matches")

    # Bilateral verification: check BOTH directions
    from app.services.matching import _permuta_atende_interesse, _imovel_atende_permuta
    bad_ab=[]  # imóvel's interesses not matched by permuta's profile
    bad_ba=[]  # permuta's criteria not matched by imóvel's profile
    for m in all_m:
        im_d=next((x for x in I if x["id"]==m["ativo_origem_id"]),None)
        pm_d=next((x for x in ALL if x["id"]==m["ativo_destino_id"]),None)
        if not im_d or not pm_d: continue
        # A→B: permuta profile vs imóvel interesses
        if im_d["interesses"]:
            if not any(_permuta_atende_interesse(pm_d, i) for i in im_d["interesses"]):
                bad_ab.append((im_d["observacoes"],pm_d["observacoes"]))
        # B→A: imóvel profile vs permuta criteria
        if not _imovel_atende_permuta(im_d, pm_d):
            bad_ba.append((im_d["observacoes"],pm_d["observacoes"]))
    print(f"\n── Bilateral A→B Violations (should be 0): {len(bad_ab)} ──")
    for b in bad_ab[:5]: print(f"  {b[0]} <-> {b[1]}")
    print(f"── Bilateral B→A Violations (should be 0): {len(bad_ba)} ──")
    for b in bad_ba[:5]: print(f"  {b[0]} <-> {b[1]}")

    mp={m["ativo_destino_id"] for m in all_m}
    um=[x for x in ALL if x["id"] not in mp]
    print(f"\n── Unmatched Permutas: {len(um)} / {len(ALL)} ──")
    for x in um:
        print(f"  {x['observacoes']:20s}  {x['cidade']}, {x.get('bairro','—')} – R${x['valor']:,.0f}")

    all_m.sort(key=lambda m:m["score"],reverse=True)
    print(f"\n── Top 10 ──")
    for m in all_m[:10]:
        io=next((x["observacoes"] for x in I if x["id"]==m["ativo_origem_id"]),"")[:18]
        po=next((x["observacoes"] for x in ALL if x["id"]==m["ativo_destino_id"]),"")[:18]
        print(f"  {m['score']:5.0f}  {io:18s}  {po:18s}  {m['justificativa'][:42]}")

    print(f"\n{'='*80}\nDONE\n{'='*80}")

if __name__=="__main__": run()
